"""Fall detection rules and optional machine learning/video services.

Heavy dependencies are imported only inside worker functions, allowing the web
application and rule based detection to run without TensorFlow or MediaPipe.
"""
from __future__ import annotations

import csv
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path
from functools import lru_cache

JOINTS = ('left_shoulder', 'right_shoulder', 'left_knee', 'right_knee')
FEATURES = [f'{joint}_{axis}' for joint in JOINTS for axis in ('x', 'y', 'v', 'vr')]
DEFAULT_CONFIG = {'MIN_OK_PARTS': 3, 'FALL_COUNT': 3, 'LS_Y': .55, 'RS_Y': .55, 'LK_Y': .65, 'RK_Y': .65, 'VISIBILITY': .7, 'FALL_PROBABILITY': .5}
THRESHOLD_KEYS = dict(zip(JOINTS, ('LS_Y', 'RS_Y', 'LK_Y', 'RK_Y')))


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name}: a numeric value is required, not a boolean.')
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name}: a numeric value is required.') from exc
    if not math.isfinite(number):
        raise ValueError(f'{name}: a finite value is required.')
    return number


def rule_predict(row, config=None):
    """Return 1 (fall), 0 (normal), or -1 (insufficient visible joints).

    This preserves the source application's rule: visibility flags are summed
    first; the number of joints below their individual y thresholds determines
    the fall label. Upper body mode uses the two shoulders only.
    """
    settings = {**DEFAULT_CONFIG, **(config or {})}
    joints = JOINTS[:2] if settings.get('mode') == 'upperbody' else JOINTS
    minimum = int((config or {}).get('MIN_OK_PARTS', 2 if len(joints) == 2 else settings['MIN_OK_PARTS']))
    if not 1 <= minimum <= len(joints):
        raise ValueError('MIN_OK_PARTS must be within the selected joint count.')
    fall_count = int((config or {}).get('FALL_COUNT', 2 if len(joints) == 2 else settings['FALL_COUNT']))
    if not 1 <= fall_count <= len(joints):
        raise ValueError('FALL_COUNT must be within the selected joint count.')
    visible = sum(_number(row.get(f'{j}_vr', 0), f'{j}_vr') for j in joints)
    if visible < minimum:
        return -1
    fallen = sum(_number(row[f'{j}_y'], f'{j}_y') >= _number(settings[THRESHOLD_KEYS[j]], THRESHOLD_KEYS[j]) for j in joints)
    return int(fallen >= fall_count)


def _tensorflow():
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise RuntimeError('Training requires optional ML packages. Run: uv sync --extra ml') from exc
    return tf


def _load_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        fields = set(reader.fieldnames or [])
        label_column = next((column for column in ('label', 'checkFall', 'checkfall') if column in fields), 'label')
        missing = set(FEATURES + [label_column]) - fields
        if missing:
            raise ValueError('CSV is missing columns: ' + ', '.join(sorted(missing)))
        data, labels = [], []
        for line, row in enumerate(reader, 2):
            label = _number(row[label_column], f'line {line} label')
            if label not in (-1, 0, 1):
                raise ValueError(f'Line {line}: label must be -1, 0, or 1.')
            if label == -1:
                continue
            data.append([_number(row[f], f'line {line} {f}') for f in FEATURES])
            labels.append(int(label))
    if len(data) < 10 or set(labels) != {0, 1}:
        raise ValueError('Training requires at least 10 labeled rows containing both normal (0) and fall (1).')
    return data, labels


def _network(tf, algorithm):
    if algorithm == 'ensemble':
        inputs = tf.keras.layers.Input(shape=(16,))
        dense = tf.keras.layers.Dense(32, activation='relu')(inputs)
        dense = tf.keras.layers.Dense(16, activation='relu')(dense)
        sequence = tf.keras.layers.Reshape((1, 16))(inputs)
        recurrent = tf.keras.layers.LSTM(32)(sequence)
        merged = tf.keras.layers.Concatenate()([dense, recurrent])
        merged = tf.keras.layers.Dense(32, activation='relu')(merged)
        output = tf.keras.layers.Dense(1, activation='sigmoid')(merged)
        return tf.keras.Model(inputs=inputs, outputs=output)
    if algorithm == 'lstm':
        return tf.keras.Sequential([tf.keras.layers.Input(shape=(1, 16)), tf.keras.layers.LSTM(32), tf.keras.layers.Dense(16, activation='relu'), tf.keras.layers.Dense(1, activation='sigmoid')])
    return tf.keras.Sequential([tf.keras.layers.Input(shape=(16,)), tf.keras.layers.Dense(32, activation='relu'), tf.keras.layers.Dense(16, activation='relu'), tf.keras.layers.Dense(1, activation='sigmoid')])


@lru_cache(maxsize=4)
def _load_bundle(bundle_path, modified_ns):
    tf = _tensorflow()
    with tempfile.TemporaryDirectory() as directory:
        with zipfile.ZipFile(bundle_path) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
            if manifest.get('features') != FEATURES:
                raise ValueError('The trained model has an incompatible feature schema.')
            algorithms = manifest['algorithms']
            if not algorithms or any(a not in ('dense', 'lstm', 'ensemble') for a in algorithms):
                raise ValueError('The model bundle contains an unsupported algorithm.')
            networks = []
            for algorithm in algorithms:
                target = Path(directory) / f'{algorithm}.keras'
                target.write_bytes(bundle.read(f'{algorithm}.keras'))
                network = tf.keras.models.load_model(target, compile=False, safe_mode=True)
                networks.append((algorithm, network))
    return manifest, networks


def _bundle_predict(bundle_path, rows):
    import numpy as np
    path = Path(bundle_path)
    manifest, networks = _load_bundle(str(path), path.stat().st_mtime_ns)
    values = np.asarray([[_number(r[f], f) for f in FEATURES] for r in rows], dtype='float32')
    scaled = (values - np.asarray(manifest['mean'])) / np.asarray(manifest['scale'])
    predictions = []
    for algorithm, network in networks:
        inputs = scaled.reshape((-1, 1, 16)) if algorithm == 'lstm' else scaled
        predictions.append(network(inputs, training=False).numpy().reshape(-1))
    return np.mean(predictions, axis=0).tolist()


def train_dataset(input_path, algorithm, config=None):
    """Train 16-feature classifiers and return a ZIP artifact plus metrics.

    The chronological validation partition is created before scaler fitting.
    This matches frame feature semantics while avoiding validation leakage.
    """
    tf = _tensorflow()
    import numpy as np
    settings = config or {}
    if algorithm not in ('dense', 'lstm', 'ensemble'):
        raise ValueError('Algorithm must be dense, lstm, or ensemble.')
    rows, labels = _load_csv(input_path)
    values = np.asarray(rows, dtype='float32')
    labels = np.asarray(labels, dtype='float32')
    split = int(len(rows) * .8)
    if set(labels[:split].tolist()) != {0., 1.}:
        raise ValueError('The first 80% of the CSV must contain both classes for training.')
    mean = values[:split].mean(axis=0)
    scale = values[:split].std(axis=0)
    scale[scale == 0] = 1.
    normalized = (values - mean) / scale
    epochs = int(settings.get('epochs', 20))
    batch_size = int(settings.get('batch_size', 32))
    if not 1 <= epochs <= 200 or not 1 <= batch_size <= 512:
        raise ValueError('epochs must be 1–200 and batch_size must be 1–512.')
    tf.keras.utils.set_random_seed(42)
    algorithms = [algorithm]
    manifest = {'version': 1, 'features': FEATURES, 'mean': mean.tolist(), 'scale': scale.tolist(), 'algorithms': algorithms, 'lstm_shape': [1, 16]}
    probabilities = []
    result = io.BytesIO()
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in algorithms:
            network = _network(tf, name)
            network.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            inputs = normalized.reshape((-1, 1, 16)) if name == 'lstm' else normalized
            network.fit(inputs[:split], labels[:split], validation_data=(inputs[split:], labels[split:]), epochs=epochs, batch_size=batch_size, verbose=0, callbacks=[tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)])
            probabilities.append(network.predict(inputs[split:], verbose=0).reshape(-1))
            artifact = Path(directory) / f'{name}.keras'
            network.save(artifact)
            bundle.write(artifact, artifact.name)
        bundle.writestr('manifest.json', json.dumps(manifest))
    guesses = np.mean(probabilities, axis=0) >= .5
    truth = labels[split:] == 1
    tp = int(np.sum(guesses & truth))
    fp = int(np.sum(guesses & ~truth))
    fn = int(np.sum(~guesses & truth))
    metrics = {'accuracy': float(np.mean(guesses == truth)), 'precision': tp / max(tp + fp, 1), 'recall': tp / max(tp + fn, 1), 'training_rows': split, 'validation_rows': len(rows) - split, 'split': 'chronological_80_20', 'validation_has_both_classes': bool(set(labels[split:].tolist()) == {0., 1.})}
    tf.keras.backend.clear_session()
    return result.getvalue(), metrics


def extract_video(input_path, config=None):
    """Extract normalized coordinates and per-frame labels into a CSV."""
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError('Video extraction requires optional packages. Run: uv sync --extra vision') from exc
    settings = {**DEFAULT_CONFIG, **(config or {})}
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        capture.release()
        raise ValueError('The uploaded video could not be opened.')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['frame', 'time_seconds', *FEATURES, 'label'])
    writer.writeheader()
    fps = capture.get(cv2.CAP_PROP_FPS)
    fps = fps if math.isfinite(fps) and fps > 0 else 30.
    counts = {'fall': 0, 'normal': 0, 'unknown': 0, 'frames': 0}
    landmark_ids = [mp.solutions.pose.PoseLandmark.LEFT_SHOULDER, mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER, mp.solutions.pose.PoseLandmark.LEFT_KNEE, mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
    try:
        with mp.solutions.pose.Pose(model_complexity=1, min_detection_confidence=.5, min_tracking_confidence=.5) as pose:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                index = counts['frames']
                if index >= int(settings.get('max_frames', 100000)):
                    raise ValueError('Video exceeds the configured frame limit (default 100000).')
                observation = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                row = {'frame': index, 'time_seconds': round(index / fps, 4)}
                for joint, landmark_id in zip(JOINTS, landmark_ids):
                    point = observation.pose_landmarks.landmark[landmark_id] if observation.pose_landmarks else None
                    row.update({f'{joint}_x': point.x if point else 0., f'{joint}_y': point.y if point else 0., f'{joint}_v': point.visibility if point else 0., f'{joint}_vr': int(point is not None and point.visibility >= float(settings['VISIBILITY']))})
                label = rule_predict(row, settings)
                row['label'] = label
                counts[{1: 'fall', 0: 'normal', -1: 'unknown'}[label]] += 1
                counts['frames'] += 1
                writer.writerow(row)
    finally:
        capture.release()
    if not counts['frames']:
        raise ValueError('The uploaded video contains no readable frames.')
    return stream.getvalue().encode('utf-8-sig'), counts


def predict_record(model, row, config=None):
    """Predict a single pose, keeping insufficient visibility as unknown."""
    label = rule_predict(row, config)
    if label == -1 or model is None:
        return label, None
    probability = float(_bundle_predict(model.artifact.path, [row])[0])
    threshold = _number((config or {}).get('FALL_PROBABILITY', .5), 'FALL_PROBABILITY')
    if not 0 <= threshold <= 1:
        raise ValueError('FALL_PROBABILITY must be between 0 and 1.')
    return int(probability >= threshold), probability


def _claim(record, kind):
    from django.utils import timezone
    from .models import Job
    if record.kind != kind:
        raise ValueError(f'This worker requires a {kind} job.')
    claimed = Job.objects.filter(pk=record.pk, status='queued').update(status='running', error='', updated_at=timezone.now())
    if not claimed:
        raise ValueError('Only queued jobs can be processed; this job was already claimed or completed.')
    record.refresh_from_db()


def _fail(record, exc):
    record.status = 'failed'
    record.error = str(exc)[:2000]
    record.save(update_fields=['status', 'error', 'updated_at'])


def train_record(record):
    from django.core.files.base import ContentFile
    from .models import TrainedModel
    _claim(record, 'train')
    try:
        artifact, metrics = train_dataset(record.input_file.path, record.algorithm, record.config)
        model = TrainedModel(owner=record.owner, job=record, name=record.name, algorithm=record.algorithm, metrics=metrics, features=FEATURES)
        model.artifact.save(f'model-{record.pk}.zip', ContentFile(artifact), save=False)
        model.save()
        record.result_file.save(f'training-{record.pk}.json', ContentFile(json.dumps(metrics, ensure_ascii=False).encode()), save=False)
        record.status = 'done'
        record.save(update_fields=['result_file', 'status', 'updated_at'])
        return model
    except Exception as exc:
        _fail(record, exc)
        raise


def process_record(record):
    from django.core.files.base import ContentFile
    _claim(record, 'video')
    try:
        artifact, counts = extract_video(record.input_file.path, record.config)
        record.result_file.save(f'poses-{record.pk}.csv', ContentFile(artifact), save=False)
        record.config = {**record.config, 'result': counts}
        record.status = 'done'
        record.save(update_fields=['result_file', 'config', 'status', 'updated_at'])
        return counts
    except Exception as exc:
        _fail(record, exc)
        raise


def extract_image(image_bytes, config=None):
    """Extract a single frame using an isolated, static MediaPipe pose instance.

    Bytes and decoded dimensions are bounded. No tracking state is shared
    between camera requests or users.
    """
    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
        raise ValueError('Camera image must contain 1 byte to 5 MB of image data.')
    width, height = _image_dimensions(image_bytes)
    if not 1 <= height <= 2048 or not 1 <= width <= 2048:
        raise ValueError('Camera image dimensions must not exceed 2048 pixels.')
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('Camera extraction requires optional packages. Run: uv sync --extra vision') from exc
    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.ndim != 3:
        raise ValueError('The submitted camera image could not be decoded.')
    height, width = frame.shape[:2]
    if not 1 <= height <= 2048 or not 1 <= width <= 2048:
        raise ValueError('Camera image dimensions must not exceed 2048 pixels.')
    visibility = _number((config or {}).get('VISIBILITY', DEFAULT_CONFIG['VISIBILITY']), 'VISIBILITY')
    if not 0 <= visibility <= 1:
        raise ValueError('VISIBILITY must be between 0 and 1.')
    ids = [mp.solutions.pose.PoseLandmark.LEFT_SHOULDER, mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER, mp.solutions.pose.PoseLandmark.LEFT_KNEE, mp.solutions.pose.PoseLandmark.RIGHT_KNEE]
    with mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=.5) as pose:
        observation = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    row = {}
    for joint, landmark_id in zip(JOINTS, ids):
        point = observation.pose_landmarks.landmark[landmark_id] if observation.pose_landmarks else None
        row.update({f'{joint}_x': point.x if point else 0., f'{joint}_y': point.y if point else 0., f'{joint}_v': point.visibility if point else 0., f'{joint}_vr': int(point is not None and point.visibility >= visibility)})
    return row


def _image_dimensions(data):
    """Inspect PNG/JPEG dimensions before allocating decoded pixel buffers."""
    import struct
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24 and data[12:16] == b'IHDR':
        return struct.unpack('>II', data[16:24])
    if data.startswith(b'\xff\xd8'):
        position = 2
        while position + 4 <= len(data):
            if data[position] != 0xff:
                break
            while position < len(data) and data[position] == 0xff:
                position += 1
            if position >= len(data):
                break
            marker = data[position]
            position += 1
            if marker in (0xd9, 0xda):
                break
            if marker == 0x01 or 0xd0 <= marker <= 0xd7:
                continue
            if position + 2 > len(data):
                break
            length = struct.unpack('>H', data[position:position + 2])[0]
            if length < 2 or position + length > len(data):
                break
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf) and length >= 7:
                height, width = struct.unpack('>HH', data[position + 3:position + 7])
                return width, height
            position += length
    raise ValueError('Camera image must be a valid JPEG or PNG.')

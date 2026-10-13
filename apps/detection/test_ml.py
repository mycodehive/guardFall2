from unittest import TestCase
from .ml import JOINTS, rule_predict


class RulePredictionTests(TestCase):
    def row(self, y=.8, visible=1):
        return {f'{joint}_{axis}': value for joint in JOINTS for axis, value in (('x', .5), ('y', y), ('v', visible), ('vr', visible))}

    def config(self, **extra):
        return {'MIN_OK_PARTS': 3, 'FALL_COUNT': 3, 'LS_Y': .5, 'RS_Y': .5, 'LK_Y': .7, 'RK_Y': .7, **extra}

    def test_fall_at_threshold_inclusive(self):
        row = self.row()
        row['left_shoulder_y'] = .5
        row['right_shoulder_y'] = .5
        row['left_knee_y'] = .7
        row['right_knee_y'] = .1
        self.assertEqual(rule_predict(row, self.config()), 1)

    def test_normal(self):
        self.assertEqual(rule_predict(self.row(y=.1), self.config()), 0)

    def test_insufficient_visibility_is_unknown(self):
        row = self.row()
        row['left_knee_vr'] = row['right_knee_vr'] = 0
        self.assertEqual(rule_predict(row, self.config()), -1)

    def test_minimum_visibility_is_inclusive(self):
        row = self.row()
        row['right_knee_vr'] = 0
        self.assertEqual(rule_predict(row, self.config()), 1)

    def test_upperbody_visibility(self):
        config = self.config(mode='upperbody', MIN_OK_PARTS=2, FALL_COUNT=2)
        self.assertEqual(rule_predict(self.row(), config), 1)
        self.assertEqual(rule_predict(self.row(visible=0), config), -1)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            rule_predict(self.row(), self.config(MIN_OK_PARTS=5))

    def test_nonfinite_value_rejected(self):
        row = self.row()
        row['left_shoulder_y'] = float('nan')
        with self.assertRaises(ValueError):
            rule_predict(row, self.config())


class TrainingCSVTests(TestCase):
    def csv_file(self, labels, replace=None):
        import csv
        import tempfile
        from .ml import FEATURES
        handle = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', suffix='.csv', delete=False)
        self.addCleanup(__import__('os').unlink, handle.name)
        writer = csv.DictWriter(handle, fieldnames=FEATURES + ['label'])
        writer.writeheader()
        for label in labels:
            row = {feature: .7 for feature in FEATURES}
            row.update(replace or {})
            row['label'] = label
            writer.writerow(row)
        handle.close()
        return handle.name

    def test_unknown_rows_excluded(self):
        from .ml import _load_csv
        rows, labels = _load_csv(self.csv_file([0, 1] * 5 + [-1]))
        self.assertEqual(len(rows), 10)
        self.assertEqual(labels, [0, 1] * 5)

    def test_single_class_rejected(self):
        from .ml import _load_csv
        with self.assertRaises(ValueError):
            _load_csv(self.csv_file([0] * 10))

    def test_nonfinite_features_rejected(self):
        from .ml import _load_csv, FEATURES
        with self.assertRaises(ValueError):
            _load_csv(self.csv_file([0, 1] * 5, {FEATURES[0]: 'inf'}))


class CameraInputValidationTests(TestCase):
    def test_boolean_feature_rejected(self):
        from .ml import _number
        with self.assertRaises(ValueError):
            _number(True, 'visibility')

    def test_invalid_image_rejected_before_optional_imports(self):
        from .ml import extract_image
        with self.assertRaises(ValueError):
            extract_image(b'not an image')

    def test_oversized_dimensions_rejected_before_decode(self):
        import struct
        from .ml import extract_image
        header = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 50000, 50000)
        with self.assertRaises(ValueError):
            extract_image(header)


class LegacyCSVTests(TestCase):
    csv_file = TrainingCSVTests.csv_file

    def test_original_checkfall_column_supported(self):
        from pathlib import Path
        from .ml import _load_csv
        for column in ('checkFall', 'checkfall'):
            with self.subTest(column=column):
                path = Path(self.csv_file([0, 1] * 5))
                path.write_text(path.read_text().replace('label', column), encoding='utf-8')
                rows, labels = _load_csv(path)
                self.assertEqual(len(rows), 10)
                self.assertEqual(set(labels), {0, 1})

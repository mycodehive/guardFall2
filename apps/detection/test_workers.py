import tempfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase,override_settings
from apps.menus.models import Menu
from .models import Job,TrainedModel
from .ml import process_record,train_record
class WorkerTests(TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.override=override_settings(MEDIA_ROOT=self.directory.name);self.override.enable()
        self.addCleanup(self.directory.cleanup);self.addCleanup(self.override.disable)
        self.user=get_user_model().objects.create_user('worker-owner',is_staff=True)
    def job(self,kind='video'):
        j=Job.objects.create(owner=self.user,name='test',kind=kind)
        j.input_file.save('test.csv' if kind=='train' else 'test.mp4',ContentFile(b'input'))
        return j
    @patch('apps.detection.ml.extract_video',return_value=(b'label\n-1\n',{'unknown':1}))
    def test_video_result_persists_and_completed_job_cannot_be_reprocessed(self,extract):
        j=self.job();process_record(j);j.refresh_from_db()
        self.assertEqual(j.status,'done');self.assertEqual(j.config['result']['unknown'],1)
        with self.assertRaises(ValueError):process_record(j)
        self.assertEqual(extract.call_count,1)
    @patch('apps.detection.ml.extract_video',side_effect=ValueError('invalid video'))
    def test_invalid_video_marks_failed(self,extract):
        j=self.job()
        with self.assertRaises(ValueError):process_record(j)
        j.refresh_from_db();self.assertEqual(j.status,'failed');self.assertIn('invalid video',j.error)
    @patch('apps.detection.ml.train_dataset',return_value=(b'ZIP-ARTIFACT',{'accuracy':.8}))
    def test_training_download_returns_model_artifact_not_metrics_json(self,train):
        j=self.job('train');model=train_record(j);j.refresh_from_db()
        self.assertEqual(j.status,'done');self.assertEqual(model.owner,self.user)
        Menu.objects.update_or_create(code='jobs',defaults={'title':'Jobs','active':True,'staff_only':True})
        self.client.force_login(self.user)
        response=self.client.get(f'/jobs/{j.pk}/download/')
        self.assertEqual(b''.join(response.streaming_content),b'ZIP-ARTIFACT');response.close()
        self.assertIn('.zip',response['Content-Disposition'])
    @patch('apps.detection.ml.extract_video')
    def test_cancelled_job_is_not_processed(self,extract):
        j=self.job();j.status='cancelled';j.save()
        with self.assertRaises(ValueError):process_record(j)
        extract.assert_not_called()

    @patch('apps.detection.ml.predict_record')
    def test_revoked_model_assignment_prevents_live_inference(self,predict):
        from .models import MonitoringSession
        from .services import ingest_frame
        from django.core.exceptions import ValidationError
        from .ml import JOINTS
        owner=get_user_model().objects.create_user('trainer')
        model=TrainedModel.objects.create(owner=owner,name='private model',active=True)
        model.allowed_users.add(self.user)
        session=MonitoringSession.objects.create(owner=self.user,model=model)
        model.allowed_users.clear()
        joints={f'{joint}_{axis}':.9 for joint in JOINTS for axis in ['x','y','v']}
        with self.assertRaises(ValidationError):ingest_frame(self.user,session.pk,0,joints)
        predict.assert_not_called();self.assertEqual(session.frames.count(),0)

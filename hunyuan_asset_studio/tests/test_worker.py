"""Contract tests with mocks, not an inference or hardware test."""
import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import trimesh
from PIL import Image
from studio import worker
from studio.core import generation_lock


class WorkerTests(unittest.TestCase):
    def test_pipeline_contract_with_mock(self):
        with tempfile.TemporaryDirectory() as root:
            image = Path(root) / 'image.png'; Image.new('RGB', (20, 20), 'white').save(image)
            calls = {}
            class Pipeline:
                @classmethod
                def from_pretrained(cls, path, **kwargs):
                    calls['load'] = (path, kwargs); return cls()
                def __call__(self, **kwargs):
                    calls['run'] = kwargs
                    kwargs['callback'](0, None, None)
                    return [trimesh.creation.box()]
            cuda = types.SimpleNamespace(is_available=lambda: True, mem_get_info=lambda: (5*2**30, 6*2**30), get_device_name=lambda _: 'test GPU', empty_cache=lambda: None)
            torch = types.SimpleNamespace(cuda=cuda, inference_mode=contextlib.nullcontext, manual_seed=lambda n: n)
            package = types.ModuleType('hy3dgen'); package.__path__ = []
            shape = types.ModuleType('hy3dgen.shapegen'); shape.Hunyuan3DDiTFlowMatchingPipeline = Pipeline
            data = {'image': str(image), 'category': 'Furniture', 'steps': 30, 'resolution': 380, 'chunks': 20000, 'seed': 12345, 'notes': ''}
            out = io.StringIO()
            with patch.dict(sys.modules, {'torch': torch, 'hy3dgen': package, 'hy3dgen.shapegen': shape}), patch.object(worker, 'verify_model'), contextlib.redirect_stdout(out):
                worker.generate(root, data)
            self.assertEqual(calls['load'][1]['subfolder'], 'hunyuan3d-dit-v2-mini')
            self.assertEqual(calls['run']['octree_resolution'], 380)
            self.assertIn('"kind": "step"', out.getvalue())
            self.assertIn('"kind": "done"', out.getvalue())
            self.assertEqual(len(list((Path(root) / 'Generated').rglob('model.glb'))), 1)

    def test_lock_prevents_another_worker(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'lock'
            with generation_lock(path):
                with self.assertRaises(RuntimeError):
                    with generation_lock(path): pass
            with generation_lock(path): pass

if __name__ == '__main__': unittest.main()

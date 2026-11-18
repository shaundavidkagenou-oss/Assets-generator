import tempfile
import unittest
import hashlib
from unittest.mock import patch
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from studio.core import initialize, validate_image, validate_mesh, save_generation, load_mesh, export_mesh, import_to_game, verify_model, atomic_json, load_settings


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = initialize(self.temp.name)
        self.image = self.root / 'input.png'; Image.new('RGBA', (20, 30), (230, 10, 10, 255)).save(self.image)
        self.mesh = trimesh.creation.box()
    def tearDown(self): self.temp.cleanup()
    def test_image_validation(self):
        self.assertEqual(validate_image(self.image).size, (20, 30))
        Image.new('RGBA', (10,10), (0,0,0,0)).save(self.image)
        with self.assertRaises(ValueError): validate_image(self.image)
        with self.assertRaises(Exception): validate_image(self.root / 'missing.png')
    def test_reject_invalid_mesh(self):
        with self.assertRaises(ValueError): validate_mesh(trimesh.Trimesh())
        mesh = self.mesh.copy(); mesh.vertices[0] = [np.nan,0,0]
        with self.assertRaises(ValueError): validate_mesh(mesh)
    def test_save_export_import_and_collision(self):
        p = save_generation(self.root, 'Buildings', self.image, self.mesh, {'seed': 3}, 'notes')
        self.assertEqual(len(load_mesh(p).faces), 12)
        for ext in ('glb', 'obj'):
            target = self.root / f'export.{ext}'
            export_mesh(p, target)
            self.assertEqual(len(load_mesh(target).faces), 12)
            with self.assertRaises(FileExistsError): export_mesh(p, target)
        game = self.root / 'game'; game.mkdir()
        copied = import_to_game(p, game); self.assertEqual(p.read_bytes(), copied.read_bytes())
        with self.assertRaises(FileExistsError): import_to_game(p, game)
    def test_failures_leave_previous_data_untouched(self):
        p = save_generation(self.root, 'Environment', self.image, self.mesh, {}, '')
        old = p.read_bytes()
        with self.assertRaises(ValueError): save_generation(self.root, '../escape', self.image, self.mesh, {}, '')
        self.assertEqual(old, p.read_bytes())
        with self.assertRaises(FileNotFoundError): verify_model(self.root)
    def test_settings(self):
        p = self.root / 'settings.json'; atomic_json(p, {'storage': 'abc', 'game_directory': 'xyz'})
        self.assertEqual(load_settings(p)['storage'], 'abc')
    def test_checksum_detects_corruption(self):
        from studio import core
        folder = core.model_dir(self.root); folder.mkdir()
        config = b'config'; weights = b'weights'
        (folder / 'config.yaml').write_bytes(config)
        (folder / 'model.fp16.safetensors').write_bytes(weights)
        git_hash = hashlib.sha1(b'blob 6\0' + config).hexdigest()
        with patch.object(core, 'CONFIG_GIT_SHA1', git_hash), patch.object(core, 'WEIGHT_SIZE', len(weights)), patch.object(core, 'WEIGHT_SHA256', hashlib.sha256(weights).hexdigest()):
            self.assertTrue(verify_model(self.root))
            (folder / 'model.fp16.safetensors').write_bytes(b'WEIGHTS')
            with self.assertRaisesRegex(ValueError, 'checksum'): verify_model(self.root)

if __name__ == '__main__': unittest.main()

"""Check the public installation contract without importing camera dependencies."""
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parent.parent


class PackagingMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))

    def test_version_and_supported_python_are_explicit(self):
        project = self.metadata['project']
        self.assertEqual(project['name'], 'hand-control-lab')
        self.assertEqual(project['version'], '0.3.1')
        self.assertEqual(project['requires-python'], '>=3.12,<3.13')

    def test_base_dependencies_match_existing_pinned_requirements(self):
        required = {line.strip() for line in (ROOT / 'requirements.txt').read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith('#')}
        self.assertEqual(set(self.metadata['project']['dependencies']), required)

    def test_live_midi_and_native_build_stay_optional(self):
        extras = self.metadata['project']['optional-dependencies']
        self.assertEqual(extras['midi'], ['mido==1.3.3', 'python-rtmidi>=1.5.8,<2'])
        self.assertEqual(extras['build'], ['PyInstaller>=6.11,<7'])
        self.assertNotIn('mido', ' '.join(self.metadata['project']['dependencies']).lower())

    def test_entry_points_preserve_gui_and_cli_choices(self):
        project = self.metadata['project']
        self.assertEqual(project['scripts']['hand-control'], 'gesture_control.desktop_entry:main')
        self.assertEqual(project['scripts']['hand-control-cli'], 'gesture_control.__main__:main')
        self.assertEqual(project['gui-scripts']['hand-control-gui'], 'gesture_control.desktop_entry:main')

    def test_discovery_keeps_tests_out_of_installed_packages(self):
        find = self.metadata['tool']['setuptools']['packages']['find']
        self.assertEqual(find['include'], ['gesture_control', 'gesture_control.*'])
        self.assertIn('tests', find['exclude'])
        self.assertFalse(find['namespaces'])

    def test_docs_and_license_are_distributed_but_models_are_not(self):
        project = self.metadata['project']
        self.assertTrue((ROOT / project['readme']).is_file())
        self.assertTrue((ROOT / project['license']['file']).is_file())
        docs = self.metadata['tool']['setuptools']['data-files']['share/doc/hand-control-lab']
        self.assertIn('docs/*.md', docs)
        manifest = (ROOT / 'MANIFEST.in').read_text()
        self.assertIn('prune models', manifest)
        self.assertIn('global-exclude *.task', manifest)
        self.assertFalse(self.metadata['tool']['setuptools']['include-package-data'])

    def test_build_backend_is_standard_setuptools(self):
        build = self.metadata['build-system']
        self.assertEqual(build['build-backend'], 'setuptools.build_meta')
        self.assertEqual(build['requires'], ['setuptools>=68'])


if __name__ == '__main__':
    unittest.main()

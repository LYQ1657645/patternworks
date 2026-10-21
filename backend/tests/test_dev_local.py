import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dev_local', ROOT / 'scripts/dev_local.py')
dev_local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_local)


def test_local_spark_uses_driver_python_and_installed_java(monkeypatch, tmp_path):
    java_home = tmp_path / '.tools/loom-java/jdk-test/Contents/Home'
    (java_home / 'bin').mkdir(parents=True)
    (java_home / 'bin/java').touch()
    monkeypatch.setattr(dev_local, 'ROOT', tmp_path)
    monkeypatch.delenv('PYSPARK_PYTHON', raising=False)
    monkeypatch.delenv('JAVA_HOME', raising=False)
    monkeypatch.setenv('PATH', '/usr/bin')

    environment = dev_local.local_runtime_environment()

    assert environment['PYSPARK_PYTHON'] == sys.executable
    assert environment['JAVA_HOME'] == str(java_home)
    assert environment['PATH'].split(':') == [str(java_home / 'bin'), '/usr/bin']


def test_explicit_python_and_valid_java_are_preserved(monkeypatch, tmp_path):
    java_home = tmp_path / 'custom-java'
    (java_home / 'bin').mkdir(parents=True)
    (java_home / 'bin/java').touch()
    monkeypatch.setattr(dev_local, 'ROOT', tmp_path)
    monkeypatch.setenv('PYSPARK_PYTHON', '/custom/python')
    monkeypatch.setenv('JAVA_HOME', str(java_home))
    monkeypatch.setenv('PATH', f'{java_home / "bin"}:/usr/bin')

    environment = dev_local.local_runtime_environment()

    assert environment['PYSPARK_PYTHON'] == '/custom/python'
    assert environment['JAVA_HOME'] == str(java_home)
    assert environment['PATH'].split(':') == [str(java_home / 'bin'), '/usr/bin']

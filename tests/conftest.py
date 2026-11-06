import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='session')
def site_dir():
    path = Path(os.environ.get('SITE_DIR', ROOT / '_site')).resolve()
    if not (path / 'index.html').is_file():
        pytest.skip(f'{path} absent : lancer build-site.py avant ces tests')
    return path


@pytest.fixture(scope='session')
def data_dir():
    path = Path(os.environ.get('DATA_DIR', ROOT / 'data')).resolve()
    if not (path / 'version.json').is_file():
        pytest.skip(f'{path} absent : lancer fetch-data.py ou fetch-latest.py avant ces tests')
    return path


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope='session')
def site_url(site_dir):
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / 'serve-local.py'), str(port), '--dir', str(site_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail('serve-local.py ne répond pas')
    yield f'http://127.0.0.1:{port}/'
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope='session')
def browser_type_launch_args(browser_type_launch_args):
    return {
        **browser_type_launch_args,
        'args': ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
    }

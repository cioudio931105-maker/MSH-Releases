"""Allowlisted offline workers for source Python and the windowed packaged EXE."""
from __future__ import annotations

from pathlib import Path
import runpy
import sys

from msh_runtime import application_root, configure_logging, configure_runtime_environment

WORKER_SCRIPTS = {
    'practical-stitch': 'microscope_stitcher_project/run_practical_stitch.py',
    'golden-compare': 'microscope_stitcher_project/tools/compare_against_golden.py',
}


def worker_command(name: str) -> list[str]:
    if name not in WORKER_SCRIPTS:
        raise ValueError('Unknown MSH offline worker')
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--msh-worker', name]
    return [sys.executable, str(application_root() / WORKER_SCRIPTS[name])]


def dispatch_worker(arguments: list[str]) -> bool:
    if arguments and arguments[0] == '--msh-environment-report':
        if len(arguments) != 2:
            raise ValueError('Environment report requires exactly one output path')
        # Software-only acceptance entry; never constructs a GUI/camera/motor object.
        from msh_environment import environment_report
        configure_runtime_environment()
        Path(arguments[1]).write_text(environment_report() + '\n', encoding='utf-8')
        return True
    if not arguments or arguments[0] != '--msh-worker':
        return False
    if len(arguments) < 2 or arguments[1] not in WORKER_SCRIPTS:
        raise ValueError('Unknown MSH offline worker')
    script = application_root() / WORKER_SCRIPTS[arguments[1]]
    if not script.is_file():
        raise FileNotFoundError(f'MSH worker source missing: {script}')
    configure_logging()
    configure_runtime_environment()
    original_args = sys.argv
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(application_root() / 'microscope_stitcher_project'))
        sys.argv = [str(script), *arguments[2:]]
        runpy.run_path(str(script), run_name='__main__')
    finally:
        sys.argv = original_args
        sys.path[:] = original_path
    return True

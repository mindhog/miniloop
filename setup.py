
from distutils.core import setup, Extension

setup(
    ext_modules = [
        Extension("_fluidsynth", sources = ['fluid.i'],
                  libraries = ['fluidsynth']
                  ),
        Extension("_alsa_midi", sources = ['alsa_midi.i'],
                  libraries = ['asound']
                  )
    ]
)
from setuptools import setup

setup(
    name='calm',
    description='Cygwin packaging maintenance tool',
    long_description=open('README.md').read(),
    author='Jon Turney',
    author_email='jon.turney@dronecode.org.uk',
    license='MIT',
    packages=['calm'],
    entry_points= {
        'console_scripts': [
            'calm = calm.calm:main',
        ],
    },
)

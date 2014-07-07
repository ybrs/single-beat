from setuptools import setup

setup(
    name='single-beat',
    version='0.1.3',
    long_description=__doc__,
    description='ensures only one instance of your process across your servers',
    url='https://github.com/ybrs/single-beat',
    packages=['singlebeat'],
    include_package_data=True,
    zip_safe=False,
    install_requires=['pyuv', 'redis'],
    entry_points={
        'console_scripts': [
            'single-beat = singlebeat.beat:run_process',
        ],
    }
)

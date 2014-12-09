from setuptools import setup

setup(
    name='single-beat',
    version='0.1.5',
    long_description=__doc__,
    description='ensures only one instance of your process across your servers',
    url='https://github.com/ybrs/single-beat',
    packages=['singlebeat'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pyuv >= 0.10, < 1.0.0',
        'redis >= 2.9.1'
    ],
    entry_points={
        'console_scripts': [
            'single-beat = singlebeat.beat:run_process',
        ],
    }
)

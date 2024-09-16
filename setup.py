"""A setuptools based setup module.

See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="mesh_persist",
    version="0.0.1",
    description="A Python project to persist Meshtastic MQTT data to a postgres DB", 
    url="https://github.com/ab0oo/mesh_persist",
    author="John Gortkos - AB0OO",
    author_email="ab0oo@ab0oo.net",
    # For a list of valid classifiers, see https://pypi.org/classifiers/
    classifiers=[  # Optional
        "Development Status :: 3 - Alpha",
        # Indicate who your project is intended for
        "Intended Audience :: Users",
        "Topic :: Software Development :: Build Tools",
        # Pick your license as you wish
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
    ],
    #keywords="sample, setuptools, development",  # Optional
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9, <4",
    install_requires=["psycopg",
                      "configparser",
                      "meshtastic"], 
    extras_require={  # Optional
        "dev": ["check-manifest"],
        "test": ["coverage"],
    },
    # If there are data files included in your packages that need to be
    # installed, specify them here.
    package_data={  # Optional
        "sample": ["package_data.dat"],
    },
    # Entry points. The following would provide a command called `sample` which
    # executes the function `main` from this package when invoked:
    entry_points={  # Optional
        "console_scripts": [
            "sample=sample:main",
        ],
    },
    project_urls={  # Optional
        "Bug Reports": "https://github.com/ab0oo/mesh_persist/issues",
        "Source": "https://github.com/ab0oo/mesh_persist/",
    },
)

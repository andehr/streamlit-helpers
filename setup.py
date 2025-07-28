from distutils.core import setup

setup(
    name='streamlithelpers',
    packages=['streamlithelpers'],
    version='0.4.2',
    license='MIT',
    description='Simple utilities to help streamlit app development',
    author='Andrew Robertson',
    author_email='',
    url='https://github.com/andehr/streamlit-helpers',
    download_url='https://github.com/andehr/streamlit-helpers/archive/refs/tags/v0.2.1.tar.gz',
    keywords=['streamlit', 'utility'],
    install_requires=[
        'pandas',
        'streamlit',
        'streamlit-extras',
        'streamlit-ace'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',  # Define that your audience are developers
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
    ],
)

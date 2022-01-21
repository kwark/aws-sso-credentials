# aws-sso-credentials

### About

Fork of https://github.com/NeilJed/aws-sso-credentials with following changes:
* added setup.py for installation with f.e. pipx (see below)
* fixed an issue where profile stored in aws credentials file contained the 'profile' prefix

For usage instructions see original project
I use it together with https://github.com/benkehoe/aws-sso-util for streamlined AWS sso usage

## Installation with pipx

I recommend you install [`pipx`](https://pipxproject.github.io/pipx/), which installs the tool in an isolated virtualenv while linking the script you need.

Mac [and Linux](https://docs.brew.sh/Homebrew-on-Linux):
```bash
brew install pipx
pipx ensurepath
```

Install
```bash
pipx install git+https://github.com/kwark/aws-sso-credentials.git
```

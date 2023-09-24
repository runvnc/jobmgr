#!/bin/bash

USER_HOME=$(eval echo ~$SUDO_USER)  # This gets the home directory of the user who invoked sudo

# Create base directory in the user's home, not root's
mkdir -p $USER_HOME/.jobmgr/output

# Only use sudo for operations that require it
sudo cp jobmgr /usr/local/bin/jobmgr

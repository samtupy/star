# STAR coagulator
The coagulator is what is responsible for networking all shared voices together with any connected user clients, the bridge between the various parts of STAR as it were.

Though a compiled coagulator.exe binary is included with the full STAR client package for windows, that is mostly used for STAR's local usage features and might not be the most convenient if you are trying to host a STAR coagulator for your team. Particularly, no support will be provided for anyone trying to run coagulator.exe through wine. Instead, it's probably best to run the coagulator from source at least on all platforms that aren't windows at this time.

The coagulator can run on windows, MacOS or Linux provided that the host machine contains a relatively modern version of python3 (3.11 works on my server, for example).

## Command line arguments
The coagulator processes a couple of command line arguments that are very useful to know about.
* --configure: This opens a terminal based configuration interface where it is possible to add and modify/delete users, as well as to alter the host and port that the server binds to. At this time you'll need to restart the coagulator after making any config changes here.
* --config /path/to/config.ini: This allows you to specify a custom location for the configuration file, by default it is just coagulator.ini along side coagulator.py/.exe.
* --authless: This temporarily disables all password authentication on the coagulator, use with care! Coagulators with no password authentication could lead to anything from DDoS attacks to voices being used nonconsentually and/or in ways that violates their license agreements, including but not limited to wasted quotas for cloud voices if someone finds your coagulator and spams it.
* --host `<host>`, --port `<port>`: Allows you to temporarily change the host and port that the coagulator binds to. For a more permanent change, use the --configure option instead.

## Windows quickstart
If you have a windows server and/or can forward ports on your home windows machine, this is the one instance where using the precompiled coagulator.exe program might be useful. You can simply press shift+f10 on the coagulator.exe file and click create shortcut, then paste that shortcut into the "shell:startup" folder for the coagulator to run every time the system boots. However, an undesireable terminal window might appear as a result of doing it this way.

Assuming you have python 3.12 or later and git installed or have [downloaded the source code](https://github.com/samtupy/star/archive/refs/heads/main.zip), you can open a command prompt up to the source code's location and do the following:
1. Create a python virtual environment: `python -m venv venv`, and activate it, `venv\scripts\activate` to isolate all modules.
2. Install the requirements, `pip install -r coagulator/requirements.txt`
3. Configure the coagulator, `python coagulator/coagulator.py --configure`

The above steps only need to be repeated once. After that, you can open a command prompt and run the coagulator with the single command `venv\scripts\python coagulator\coagulator.py` or if you do activate the virtual environment, simply `python coagulator/coagulator.py`

If you'd like to get rid of the terminal window, you can run  the coagulator using the pythonw command instead of just python, for example `pythonw coagulator/coagulator.py`

## MacOS and Linux quickstart
The instructions on MacOS and Linux are pretty much the same. Similar to above, you should clone the github repository or download the sourcecode as a zip, and cd to that directory in a terminal.
1. Create a virtual environment, `python3 -m venv venv` and activate it, `source venv/bin/activate` in this case. You might get an error on Linux about needing to install the python3-venv package, if so you should follow that instruction and use apt-get or your package manager of choice to install the package it indicates before executing the venv creation command again.
2. Install the requirements, `pip install -r coagulator/requirements.txt`
3. Configure the coagulator, `python coagulator/coagulator.py --configure`

Again when you are just running the coagulator in the future, you can skip the venv activation if you like by running `venv/bin/python coagulator/coagulator.py`

## Linux systemd unit
On linux, a systemd .service file is provided if you want the coagulator you are hosting to run automatically when your server reboots.

1. You will need to modify starserver.service in the coagulator directory of the repository and make it point to an existing user on your system. That user should have the star repository cloned in their home directory, or else you can modify the .service file further as you see fit if you'd like it somewhere else.
2. Copy the modified starserver.service file to /etc/systemd/system
3. Configure the coagulator with the same command as usual.
4. Run `sudo systemd start starserver` to bring the server up, `sudo systemd stop starserver` to bring the server down, `sudo systemctl enable starserver` to make the server auto start on boot, or `sudo systemctl disable starserver` to prevent the auto start.

## Sharing your coagulator's URI and other tips
Both the user client and STAR providers connect to your coagulator using standardized URI syntax with the WebSocket (ws) scheme. That is, a valid URI might look like ws://username:password@address:port.

So if your server has the IP address 2.3.4.5 and you host a coagulator on the default port (7774) with a user named 'joe' who has a password of 'DoNotHackMeBro', you could send joe the URI ws://joe:DoNotHackMeBro@2.3.4.5:7774 which they can just paste into the host field in their client or provider configuration.

It might be best to avoid passwords with special characters for now, as such characters need to be URL encoded making them more difficult to type in URI form. For example if a password has an @ character in it such as 'my_password@secure', the uri would look like ws://user:my_password%40secure@host:port, otherwise as you can imagine the system would get confused and think that the word secure after the first @ character was part of the address!

Please be aware that as this application does not protect anything particularly sensative, passwords are stored in plain-text in the coagulator's configuration file at this time. As such, avoid the usage of passwords that are similar to those that might be used elsewhere for more sensative services.

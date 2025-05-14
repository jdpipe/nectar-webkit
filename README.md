# Guacamole App for ARDC Nectar virtual desktops

This small script implements a way to access Nectar's virtual desktops (Guacamole remote access software) from inside a dedicated GtkWebKit window in Ubuntu Linux. It was tested with Ubuntu 20.04.

* You can get true full screen view by typing ctrl-super-F11; type this again to exist full screen.
* The script intercepts GNOME alt-tab and related keystrokes and passes them to the Gaucamole client, to improve keyboard usability. When the script exits full screen mode, the keybindings are restored.
* The script performs authentication via the web browser by default, or it can be done in the WebKit app window if preferred -- use the command-line arguments. Via the app is preferred since you probably have Microsoft authentication cookies etc there and will be able to reconnect to your virtual machine more smoothly using that route.

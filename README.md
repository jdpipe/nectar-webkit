# Guacamole App for ARDC Nectar virtual desktops

This small script implements a way to access Nectar's virtual desktops (Guacamole remote access software) from inside a dedicated GtkWebKit window in Ubuntu Linux. It was tested with Ubuntu 20.04.

* You can get true full screen view by typing ctrl-super-F11; type this again to exist full screen.
* The script intercepts GNOME alt-tab and related keystrokes and passes them to the Gaucamole client, to improve keyboard usability. When the script exits full screen mode, the keybindings are restored.
* The script performs authentication via the WebKit app window. Efforts to re-use OAuth tokens that exist in the user's browser were unsuccessful, apparently because of limitatins imposed by the Nectar administrators.



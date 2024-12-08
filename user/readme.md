# STAR user client documentation
The STAR user client is the frontend interface to this relay system. With it, you can connect to any coagulator you know about before synthesizing text into either audio that is played through speakers or rendered to audio files.

Almost all of the star client's functionality can be accessed via keyboard shortcuts.

## First time run instructions
To run the STAR client, simply click on STAR.exe or the equivalent on other platforms.

The first time the client is executed, you will see a simple screen with a status message informing you that the host is not configured, along with 2 buttons (Options and Exit). It is required that a valid configuration file exist to use this client, so one pass through the options dialog is needed.

You will want to click the options button, then set a valid host address to connect to, "ws://user:password@samtupy.com:7774" withoutt the quotes, for example.

Once you've done clicked OK in the options dialog after setting a host, you will be returned to the main STAR client screen accept that the status message will have now switched to the word connecting. When a connection is successfully established, the true main screen of STAR will appear.

From this point the host you've set is stored in a configuration file, so further launches of the client will instantly connect to the host you've configured.

## Main client screen
Once you've successfully connected to a remote coagulator, you will be presented with the actual main client interface, which contains access to the bulkk of the programs functionality.

From here, you can:
* Enumerate and preview all available voices
* Speak custom text through the currently focused voice.
* Provide a full script in play like format which can be either previewed live or rendered to either a directory of audio files or a single consolidated track.
* Access further configuration options.

## Options dialog
This dialog contains several options you can configure to customize the client, with the only one you are required to alter being host. You can access it at any time by pressing alt+o from the client's main screen. The controls are as follows:

* host (alt+h): This field denotes the remote coagulator address that the client should connect to. It is expected to be invalid URI form and the STAR system uses websockets. A valid uri might therefor look like "ws://user:password@samtupy.com:7774" without the quotes, for example. Ws:// denotes a websocket connection, user:password is the authentication info, followed by the server's host and port.
* default render location (alt+r): Where should rendered output files be saved? The directory you specify will be created upon the first render if it does not already exist.
* render filename template (alt+f): This field allows you to control the filenames used for rendered output. A .wav wxtension is automatically added to the filename so the template should not include that. Further documentation on this setting is included in the dialog in the render filename template tokens information field.
* voice preview text (alt+p): The text that should be spoken when previewing an available voice, `{voice}` will be replaced with the name of the voice being previewed.
* output_device (alt+o): This control allows you to select the sound output device that the client will play sound and speech through. At this time any currently playing audio will not switch to the new device, but any future audio will use it.
* clear output subdirectory on render (alt+s): If this is unchecked and if you specify a subdirectory for rendering, the subdirectory you specify will not be cleared when rendering takes place, which could preserve content you didn't intend to delete at the expense of extra clutter.
* Clear audio cache (alt+c): This deletes all cached speech phrases in memory. You might want to do this if your client is taking too much ram, or if a voice might sound different if a cached string were to be resynthesized.


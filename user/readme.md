# STAR user client documentation
The STAR user client is the frontend interface to this relay system. With it, you can connect to any coagulator you know about before synthesizing text into either audio that is played through speakers or rendered to audio files.

If you are trying to learn how to host a coagulator so that your friends can share voices, then this [coagulator quickstart guide](https://github.com/samtupy/star/blob/main/coagulator/readme.md) on STAR's github will help you do that.

Almost all of the star client's functionality can be accessed via keyboard shortcuts, usually alt+letter.

## First time run instructions
To run the STAR client, simply click on STAR.exe or the equivalent on other platforms.

The first time the client is executed, you will see a simple screen with a status message informing you that the host is not configured, along with 3 buttons (Run locally, Options and Exit). If you are not part of a group and do not wish to use STAR's networking features, simply click Run Locally and you should be set to go! Otherwise, it is required that a valid configuration file containing at least one remote host exists to use this client, so one pass through the options dialog is needed. In that case you will want to click the options button, then set a valid host address to connect to, "ws://user:password@samtupy.com:7774" withoutt the quotes, for example.

Once you've clicked the Run Locally button or else OK in the options dialog after setting a host, you will be returned to the main STAR client screen if applicable accept that the status message will have now switched to the word connecting. When a connection is successfully established, the true main screen of STAR will appear.

From this point your connection choice is stored in a configuration file, meaning that restarting the STAR client will simply reconnect to the saved host or spin up a local coagulator and providers and connect to that based on your saved preference. You can of course change this preference from the options dialog at any time.

## Main client screen
Once you've successfully connected to a remote coagulator, you will be presented with the actual main client interface, which contains access to the bulkk of the programs functionality.

From here, you can:
* Enumerate and preview all available voices
* Speak custom text through the currently focused voice.
* Provide a full script in play like format which can be either previewed live or rendered to either a directory of audio files or a single consolidated track.
* Access further configuration options.

The controls on this screen are as follows:
* voices (alt+v): This list contains all remotely available voices you are connected to. You can press ctrl+c on any of them to copy the voice name to clipboard, and ctrl+f as well as f3 and shift+f3 allow you to search the voice list.
* quickspeak (alt+q): This text field allows you to speak text through the currently selected voice. Choose a voice in the voices list, type text in the quickspeak field and press enter to speak the text you have typed.
* enter script (alt+s): Here, you can type or paste a full line-by-line play like script to preview or render. The format for these scripts is described in another section in this document, but the basic gist is voicename: text on each line for example "Sam: Hi, I'm Sam!" You can press ctrl+alt+up arrow, down arrow, space, or enter to preview the script in real time. ctrl+alt+up and down arrows preview by line, ctrl+alt+space previews the currently focused line, and ctrl+alt+enter acts like a say-all, previewing the script automatically line by line until an error is encountered or the end of the script is reached.
* output subdirectory or consolidated filename (alt+d): Here, you can choose specifically where the output of the next render will be placed within the global render output directory. If it's left empty, new .wav files will be added to the root of the globally configured output directory that is specified in the options dialog. Otherwise a subdirectory with the name specified in this field will be created to store new output. If the contents of this field end with a .wav (or even .mp3 if you have ffmpeg on your computer), all speech clips will be consolidated into the one filename specified instead of as individual .wav files.
* render to disc (alt+r): This button begins the process of synthesizing and rendering any script text that's been provided. It's label will switch to "Cancel" when rendering is in progress.
* options (alt+o): Open the options dialog.
* exit (alt+e): Exit the program, can also be done with alt+f4 or escape. When using the run locally option it's always best to exit cleanly rather than killing the process in task manager or ctrl+c in the terminal etc, otherwise the local coagulator and providers launched by the client won't be terminated properly and you'll then need to kill them yourself.

You can also press alt+backspace to pause or resume any playing speech from any place in the main screen.

## Options dialog
This dialog contains several options you can configure to customize the client, with the only one you are required to alter being host. You can access it at any time by pressing alt+o from the client's main screen. The controls are as follows:

* host (alt+h): This field denotes the remote coagulator address that the client should connect to. Other than the special string "local" which runs all the STAR components on your local computer if possible, it is expected to be invalid URI form and the STAR system uses websockets. A valid uri might therefor look like "ws://user:password@samtupy.com:7774" without the quotes, for example. Ws:// denotes a websocket connection, user:password is the authentication info, followed by the server's host and port. This is a combo box that also lets you select from previously connected hosts. When a previously connected host is selected, a delete saved host (alt+d) button will appear next to the host control which allows you to keep your saved hosts list clean.
* default render location (alt+r): Where should rendered output files be saved? The directory you specify will be created upon the first render if it does not already exist. You can use the browse button next to the text field to search your filesystem without typing or pasting a path.
* render filename template (alt+f): This field allows you to control the filenames used for rendered output. A .wav extension is automatically added to the filename so the template should not include that. Further documentation on this setting is included in the dialog in the render filename template tokens information field.
* amount of silence (in milliseconds) to insert between consolidated speech clips (alt+e): This spin control allows you to customize the amount of silence that seperates speech clips from each other when the option of creating a single long running file rather than individual audio clips is used.
* voice preview text (alt+p): The text that should be spoken when previewing an available voice, `{voice}` will be replaced with the name of the voice being previewed.
* output_device (alt+o): This control allows you to select the sound output device that the client will play sound and speech through. At this time any currently playing audio will not switch to the new device, but any future audio will use it.
* clear output subdirectory on render (alt+s): If this is unchecked and if you specify a subdirectory for rendering, the subdirectory you specify will not be cleared when rendering takes place, which could preserve content you didn't intend to delete at the expense of extra clutter.
* Clear audio cache (alt+c): This deletes all cached speech phrases in memory. You might want to do this if your client is taking too much ram, or if a voice might sound different if a cached string were to be resynthesized. The option may be invisible in the dialog's tab order if the cache is already empty.

## Script format
The main function of this program involves being able to provide sevral lines of speech (all with different voices and parameters) that are then synthesized to wav files for use in dramatized tts audio productions.

To facilitate this, STAR parses the text in the script field based on a simple specification that allows the end user to denote what voice each line of text is spoken with, and what parameters such as rate and pitch should be applied to that line.

### Basic line definition
A typical line looks like:

```Microsoft Sam: Hello, everybody knows me!```

First a voice name is provided, then a colon and a space to denote the end of the voice name, and then the text that should be synthesized on that line. Only a partial voice name is required, for example the voice name "david" would resolve to "Microsoft David Desktop English United States."

### Voice parameters
It is also possible to provide parameters to the voice, for example to make Microsoft sam speak slower one might type:

```Microsoft Sam<r=-5>: Aaaawch, that hurts!```

The available parameters are r for rate and p for pitch, though the minimum and maximum values or even whether the parameters are supported is left up to each STAR provider/speech engine. Each parameter=value pair should be seperated by space if a line contains more than one of them, for example `<rp1 p=5>` to make a voice speak slightly faster and significantly higher in pitch.

### Comments and whitespace
If the first non-whitespace character in a line is a semicolon (;), STAR will treat the line as a comment and will not process it.

Whitespace at the beginning of all lines is trimmed during parsing, meaning that indenting parts of your script is possible should you desire.

### Selecting between multiple voice occurances
A common issue involves selecting the appropriate/desired voice based on a similar list of possible voices. For example, one voice might be called "Paul" while another is called "Espeak Paul English US." In this case, you can put a numeric specifier before a voice name to select alternate occurances of that voice. Such a line might look like:

```2.david: Hi, I am the second david!```

### Voice aliases
The next great feature supported in these scripts is voice aliases or character names. This allows you to refer to a voice by a shorthand identifier instead of by either a full voice name or a numeric identifier which might change based on what voices are connected. If the first non-whitespace character on a line begins with a verticle bar (|), the line is treated as extra metadata instead of as a speech line. The only currently supported metadata is the definition of a voice alias. For example, consider this script:

```;characters:
	|john = Adult Male #8, American English TruVoice
	|rs5 = RoboSoft Five
	|sam=Microsoft Sam
;scene
	John: aaaaaa I'm being attacked by a robot!
	rs5: Get ready, for you will die now!
	Sam: I'll save you!
	rs5: nooooooooooooooaaaaaooooo!
	John: Thanks Sam.
```

The above example shows the usage of comments to denote the characters from the scenes, and shows how by defining the character alias rs5 for example, we can then avoid needing to type RoboSoft Five over and over again in the script which can be a huge speed boost. Any whitespace is trimmed from the aliases so that space between the equals sign is optional, and an alias defined anywhere in your script will effect the entire document E. you can safely place your aliases at the bottom of your script if you like. Aliases can include default rate and pitch parameters, such as `|MadMike = Microsoft Mike<p=9 r=3>` for example. If a script line then contains any parameters, that line will override the defaults in the voice alias.

### Balabolka / balcon tags
Though they will not be fully explained here as Balabolka provides it's own documentation, it is worth noting that it is possible to use the typical voice tags supported by the Balabolka program, with the exception of the {{Audio=}} tag. For example,

`Sam: Hi there, that's cool! {{Voice=mary}} yeah it really is!`

Would cause the voice to switch from Sam to mary half way through synthesis.

If you really want to get the {{Audio=}} tag working with the balcony provider, you must [download balcon.zip](https://www.cross-plus-a.com/balcon.zip) and place the libsamplerate.dll file alongside balcon.exe. Be sure you really want to do this though particularly if you want to share voices with others, as it provides access to any audio file on your system given a path! For example, if the audio tag is enabled, the following line would embed the specified sounds into the generated stream.

`Sam: Hi there, {{Audio=C:\Windows\Media\Chord.wav}} that's cool! {{Voice=mary}} yeah it really is! {{Audio=C:\windows\media\notify.wav}}`

### Selective rendering
The final supported feature in the script format allows for selective rendering. Often, it might happen that you might want to simply tweak one or 2 lines, or continuously add new voice clips to your audio production as you are sound designing. While you could just paste only the part of your script in the field you wish to render, this would mess up any counters which would allow you to account for what order the voice clips should play in. Instead, you can wrap groups of lines in `< and >` characters to select only the lines contained within to render, like this.

```;characters:
	|john = Adult Male #8, American English TruVoice
	|rs5 = RoboSoft Five
	|sam=Microsoft Sam
;scene
	John: aaaaaa I'm being attacked by a robot!
	rs5: Get ready, for you will die now!
	Sam: I'll save you!
	rs5: nooooooooooooooaaaaaooooo!
	John: Thanks Sam.
	<
	Sam: You're welcome, but now as payment you must go publicly proclaim me to be the best tts voice that's ever existed!
	John: Are you kidding? Dream on!
	>
```

Here, we've selected only the 2 final lines in the script for rendering, but those lines will maintain the proper file counter. While this is also useful for editing existing lines, it may be somewhat less useful when trying to add lines in the middle of your script as doing so will invalidate the incrementing file/clip counter for any lines after the addition/deletion point. You can have as many blocks of selected lines as you wish. Another useful trick with this is that you can effectively disable render selection blocks without deleting them. Since any nesting levels of `< and >` characters are ignored, you can first wrap some lines you wish to render in selection blocks, which will cause only those lines to be rendered. Then however if you place one large selection block around your entire script, now in effect your entire script will be rendered again, with the ability to simply remove the selection tokens from the beginning and end of the document to reenable the previously configured render selection blocks.

## Sharing voices
The STAR client package comes shipped with a couple of voice providers, making it easy to allow your computer's voices to be used by anybody else using the same coagulator as you are.

In the windows package, these are balcony.exe and sammy.exe. For MacOS voice sharing, currently you will need to download the STAR source code and run the macsay.py provider in your mac's terminal.

Each provider has a --configure command line option. So if you run balcony.exe --configure, for example, a dialog will appear allowing you to:
1. Add, edit and remove hosts. A provider can connect to multiple coagulators at once!
2. Disable certain voices from being shared.
3. Cause any voice to be shared with a different name or alias than the default.

You can then run balcony.exe or sam.exe standalone and the voices will be shared using the set configuration. It's common to create shortcuts to the providers and place them in the shell:startup location accessible from the run dialog, causing voices to be shared to a list of coagulators on system boot.

## Change log
### Revision 3
This is a major update to STAR which includes a complete user client rewrite and consequently the introduction of several useful features.
* The user client was completely rewritten from scratch in python and WX Widgets, meaning that though feedback must still be gathered to make it look right or even to insure that controls are visible at all, the user client should soon  be able to be used without a screen reader within a couple of revisions!
* Due to the script text field being a true richtext control, the previewing hotkeys were changed to control+alt+up, down, and space rather than just control. This was forced on us because NVDA at least seems to always speak when control+up and down are pressed on a text field regardless of any application code.
* It is now possible to press ctrl+alt+enter on any valid speech line in the script to begin auto previewing the entire script up to it's end or the next error.
* You can press alt+backspace anywhere in the main screen to pause and resume any playing speech, thus the stop currently playing speech button was removed from the interface.
* The STAR client can now run all needed components such as the coagulator and providers locally with one click, meaning that STAR should require 0 extra setup assuming you just want to use only the voices on your computer!
* There is now an options dialog with various customizations you can make from the render filename template to the default render output location to the voice preview text and more.
* Now that the options dialog exists, the output device list has been moved to that dialog.
* It is now possible to consolidate the entire script into one audio file! Next to the script field, there is an output subdirectory or consolidated filename field. If you set thhis to a filename such as output.wav instead of a folder name such as output, now a single output.wav file will be created containing all voice clips seperated by a configurable amount of silence.
* The synthesis caching is much improved. Now if you preview a script before rendering it, the render will be almost instant as the cached phrases from the synthesis will now be used while rendering. It is also possible to manually clear the audio cache in the options dialog.
* The render progress sound was removed in favor of a real native progress bar. It sounds a bit less cool but should be visually accessible soon and is far less expensive than playing the sound.
* There are some cool new features in the script syntax, such as selecting only certain lines to render on the minor end to being able to define character aliases per script on the very useful end!
* Typically STAR coagulators now require authentication. To make dealing with this easier, STAR can now save previous hosts you connect to, allowing you to select between them in the options dialog.
* Full documentation is now provided as well as automatic windows client builds on Github.

## Disclaimer
This is a tool created with the intention of making it possible for small groups of friends to create tts audio skits and dramas with increased colaberation, or even so that somebody can network all of their local voices together with fewer cables and hastles. By no means is this intended to deprive voice creators of income / hurt them in any way / disrespect their terms of service. Sharing access to voices that disallow such distrobution in their license agreements, particularly beyond small groups of friends, goes against the intended use I had in mind for this project and I expressly disclaim any responsibility for such misuse of the program. Please use this tool respectfully!

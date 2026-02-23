# Speech To Audio Relay (STAR)
[Download windows client](https://github.com/samtupy/star/releases/latest/download/STAR_win64_v4.zip)

This is a set of components intended to ease the creation of audio productions that involve the synthesis of text to speech to audio, particularly where many voices that might be contained on any number of different computers or devices are involved.

## How it Works

This setup involves 3 components:

### User client
The frontend to this application involves the user client. This application is responsible for requesting synthesis and outputting the results. Separate [user client documentation](user/readme.md) is provided which also explains the script syntax.

### Speech Providers
The task of these components is to translate text to speech depending on the voices available on a given system. A provider can run anywhere TTS voices are available, and some providers might be platform-agnostic as they might synthesize tts from cloud providers like Google or Amazon.

### Coagulation server
This component is what ties everything together. A coagulator is run, and then speech providers connect to it and send a list of voices it can synthesize. The coagulator will take note of voice names to provider clients. When a user client connects to the coagulator, it can therefor send a long speech script to the coagulator which is then parsed, whereupon requests per voice are sent on to the various speech providers that can synthesize each voice. The coagulator then acts as a relay, sending the audio data from each provider back to the user client that initially asked for it.

In more simple terms it's just the server that lets providers from anywhere communicate with user clients. There is [separate coagulator documentation](https://github.com/samtupy/star/blob/main/coagulator/readme.md) here if you want to learn how to host one yourself.

## Running from Source
Currently the client works with python 3.12 windows 64 bit, however it should work on other platforms soon once a few minor dependancy issues are resolved.

Pretty much this entire project is written in python sans a couple of providers such as the one for the NVGT fallback RSynth voice. The recommended first-time instructions are as follows:
1. After opening a terminal window up to this repository's directory, create a python virtual environment to make an isolated workspace for all modules this project uses: `python -m venv venv`
2. Activate the virtual environment you just created: on windows `venv\scripts\activate`, or on MacOS/Linux `source venv/bin/activate`
3. Install requirements: `pip install -r requirements.txt`
4. If you wish to run the balcony provider on windows, you'll want to download [balcon.zip](https://www.cross-plus-a.com/balcon.zip) and place the contained balcon.exe in the provider/balcony directory. As of Dec 09 2024 an update to balcon causes an extra charset detection component (chsdet.dll) to also be required, so if you want to avoid that you can use the [balcon.exe used in STAR's CI actions](https://samtupy.com/star_ci/balcon.exe) instead. WARNING! If you place libsamplerate.dll from the balcon distrobution alongside balcon.exe, balcon's `{{Audio=path}}` tag will begin working, meaning that anyone sharing their voices might also be sharing any audio file on their system that somebody knows the path to (a HUGE security risk)! Only put this DLL in place for local setups or hwen you are absolutely sure everyone on your network can be trusted. The dll is not included in the public STAR distrobution.
5. If you want to use the sammy provider, you need the sam.exe synthesizer. You can just download the one the build workflow uses [from here](https://samtupy.com/star_ci/sam.exe) if you like, or else I built that from [this repository](https://github.com/s-macke/SAM) with the SConstruct line `Program("sam", Glob("src/*.c"), CPPFLAGS = ["/Os"])` if you'd rather build it yourself. Regardless, you'll want to place sam.exe in the provider/sammy folder.

From this point you can cd to the coagulator directory and run coagulator.py, cd to the provider directory and run balcony/balcony.py or macsay/macsay.py, or cd to the user directory and run STAR.py based on what you want to do. You'll likely want to configure the coagulator/provider first, and so everything accept the user client supports a --configure command line argument which brings up a configuration interface, and/or --config filename.ini to load configuration from a specified path (useful for things like unix daemons).

If you want to create a complete local stack in one shell window, at least on windows you can use pythonw instead of python to run the coagulator and the provider in windows mode which will not block your terminal.

If you wish to build the binaries, you can run `/.build.bat` on windows or `pyinstaller --noconfirm STAR.spec` on other platforms from the repository's root directory after generating the readme.html file by running python user/html_readme.py.

You only need to set up a virtual environment the first time you clone the repository, after which you only need to activate it every time you open a terminal window up to the root of the repository.

## API
You can skip this section unless you wish to contribute to the project, want to know how it works, or intend to write new providers or clients.

This project uses web sockets for communication. The coagulator is what acts as the web socket server, and is written in python. Both speech providers and user clients connect to it. All payloads accept for the audio data itself are in json, and I can't imagine a way to make the API any more simple.

### Writing a user client
For a user client to communicate with the coagulator, it should send a payload in the form:

```{"user": revision, "request": ["voice1: line1", "voice2: line2", "someone<r=-5>": "etc"]}```

If the request key is omited, the coagulator will return a list of full voice names available in the form `{"voices": ["voice1", "voice2"]}`

Otherwise, the coagulator will start sending back binary payloads in the form:

```2 byte little endian request ID length, request ID, audio data```

Or,

```2 byte little endian metadata length, metadata, audio data```

where metadata is a json payload in the form:

```{"id": ID, "extension": "mp3"}```

Until all lines passed have been synthesized.

While the coagulator does act as a direct relay and thus providers could send data in any format it wants, what's written here is the standard.

The speech key is important. It contains an ID used to track the order of synthesis. It is made up of 2 or at most 3 numbers separated by an underscore. The first number usually isn't importaant, it's the integer client ID that you are known as by the coagulator. If it exists, the second number contains any custom ID you have passed by providing an ID key in your request message. The final number however contains an integer that denotes the fragment number that this speech payload is referencing. When outputting data without providing an ID in your requests, you should number or sequence your output based on this final number.

### Writing a speech provider in python
The recommended way to write a STAR provider is by using the existing framework called provider.py within the provider directory. Several example providers already exist which not only connect most popular voice engines to STAR, but which can also be used as examples of creating your own provider.

If you have a command line program which can receive text as input and which produces audio data as output, a provider can be written in just a couple lines of code. The following is a 2 line provider which wraps the sam.exe synthesizer, for example.

```Python
from provider import star_provider
star_provider("sammy", voices = "microsam", synthesis_process = ["sam", "-wav", "{filename}", "{text}"], synthesis_process_rate = ["-speed", "{rate}"], synthesis_process_pitch = ["-pitch", "{pitch}"])
```

The constructor for the STAR provider class is as follows:

`def __init__(self, provider_basename = os.path.splitext(sys.argv[0])[0], handle_argv = True, run_immedietly = True, voices = None, synthesis_process = None, synthesis_process_rate = None, synthesis_process_pitch = None, synthesis_default_rate = None, synthesis_default_pitch = None, synthesis_audio_extension = None)`

Arguments:
* provider_basename: This is used to name the provider's configuration file, show error messages, or anything else where a generic name string can be useful. Should be a valid file basename.
* handle_argv: By default, the provided provider facility can handle various command line arguments which control things like what config file to load and more. You can disable this switch if you want to disable this for your provider.
* run_immedietly: If you set this to False, you'll need to manually call provider.run() after the provider has been constructed, which could be good if you wish to further configure it before starting it up.
* voices: An initial list of voices you provide. For more dynamic providers where the list could change, it's best to instead override the provider's get_voices method.
* synthesis_process: If your provider is simply connecting to a command line application, this argument controls the process that is to be executed. It should be a list, with one part of the command per item. The first item is usually a process filename, with consecutive items being arguments that are passed to the given filename. The format specifiers {filename}, {text}, {rate}, {pitch} can be used to insert the dynamic bits of the argument content however it's best to use the synthesis_process_rate and synthesis_process_pitch provider arguments to handle the speech parameters instead of bundling them all in the synthesis_process argument directly.
* synthesis_process_rate, synthesis_process_pitch: Additions to the synthesis_process argument, these arguments are only appended to the final command that is to be executed only if the rate and/or pitch are actually present in the request. This might be important because with most command line applications, not specifying a rate or pitch argument at all means using the default, therefor the provider's default value of 0 for these parameters if they are not present might not be optimal for calling your synthesis process. Just like above you use {rate} or {pitch} to actually insert that value into the argument string, and you should pass arguments as a python list.
* synthesis_default_rate, synthesis_default_pitch: default values passed to the synthesize function when rate or pitch is omitted in an individual speech request. This is useful in some sanarios where the default rate or pitch of a voice is indeterminet or based on some global system setting, meaning that the synthesis could sound different for each person providing such a voice if a default parameter value is not enforced.
* synthesis_audio_extension: This hint is eventually passed along to user clients upon synthesis, telling them what file extension to save speech clips as that have been received by your provider. Should be mp3, ogg, opus etc. A value of None (the default) is the same as wav.

You might be interested in overriding the following methods in a subclass of the star_provider object if you need more advanced functionality than what the base object provides:
* def synthesize(self, voice, text, rate = None, pitch = None): This method can return a bytes like object containing synthesized wave data, or an error string if synthesis was not successful. The voice argument is garenteed to be set to one of the voices you told the provider about.
* def get_voices(self): This function can either return a single voice name as a string, a list of voice names, or a dictionary with the key being a voice name and the value being a subdictionary with extra metadata about the voice (E for language codes etc in future).

Both of these functions can be async if necessary.

### Writing a speech provider from scratch
Usually, it's best to inherit from the provided python provider class rather than doing this from scratch, but below are the instructions nevertheless which can be useful for example if you wish to write a provider that runs on an embedded device or in any other environment where modern python is not available.

When a speech provider first connects to a coagulator, it should send a packet in the form:

```{"provider": revision, "provider_name": "balcony" or "macsay" or "your_basename_here", "voices": ["voice1", "voice2", "etc"]}```

before continuously listening for packets in the form:

```{"voice": "voicename", "text": "text to speak", "id": ID}```

and responding each time with binary packets such as:

```2 byte little endian ID length, ID, audio data```

where ID is the same as that received in the voice packet's id key.

Or,

```2 byte little endian metadata length, metadata, audio data```

where metadata is a json payload in the form:

```{"id": ID, "extension": "mp3"}```

Voice packets might contain extra parameters like rate and pitch, but your providers should be set up to not require these.

If a request fails to synthesize or if you wish to pipe status messages back to the client that initiated a speech request, you can send packets such as:

```{"provider": revision, "id": request_ID, "status": "status message"}```

Another special key, "abort", can be sent in this payload with a value of True to indicate that this speech request has failed and thus that no audio data will be forthcoming.

## Disclaimer
This is a tool created with the intention of making it possible for small groups of friends to create tts audio skits and dramas with increased colaberation, or even so that somebody can network all of their local voices together with fewer cables and hastles. By no means is this intended to deprive voice creators of income / hurt them in any way / disrespect their terms of service. Sharing access to voices that disallow such distrobution in their license agreements, particularly beyond small groups of friends, goes against the intended use I had in mind for this project and I expressly disclaim any responsibility for such misuse of the program. Please use this tool respectfully!

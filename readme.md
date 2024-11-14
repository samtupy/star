## WARNING!
This repository is under heavy development as I work on polishing this project. Until this notice disappears, please expect documentation to be incomplete/out of date and understand that you may find this program confusing to build / use and I will likely provide little support until documentation and polishing is complete.

# Speech To Audio Relay (STAR)
This is a set of components intended to ease the creation of audio productions that involve the synthesis of text to speech to audio, particularly where many voices that might be contained on any number of different computers or devices are involved.

This setup involves 3 components:

## User client
The frontend to this application involves the user client. This application is responsible for requesting synthesis and outputting the results.

## Speech Providers
The task of these components is to translate text to speech depending on the voices available on a given system. A provider can run anywhere TTS voices are available, and some providers might be platform-agnostic as they might synthesize tts from cloud providers like Google or Amazon.

## Coagulation server
This component is what ties everything together. A coagulator is run, and then speech providers connect to it and send a list of voices it can synthesize. The coagulator will take note of voice names to provider clients. When a user client connects to the coagulator, it can therefor send a long speech script to the coagulator which is then parsed, whereupon requests per voice are sent on to the various speech providers that can synthesize each voices. The coagulator then acts as a relay, sending the audio data from each provider back to the user client that initially asked for it.

## API

This project uses web sockets for communication. The coagulator is what acts as the web socket server, and is written in python. Both speech providers and user clients connect to it. All payloads are in json, and I can't imagine a way to make the API any more simple.

### Writing a user client
For a user client to communicate with the coagulator, it should send a payload in the form:
```{"user": revision, "request": ["voice1: line1", "voice2: line2", "someone<r=-5>": "etc"]}```
If the text key is omited, the coagulator will return a list of full voice names available in the form `{"voices": ["voice1", "voice2"]}`

Otherwise, the coagulator will start sending back payloads in the form:
```{"speech": ID, "data": BASE64_ENCODED_WAV}```
Until all lines passed have been synthesized.

While the coagulator does act as a direct relay and thus providers could send data in any format it wants and could even include extra keys in the response, what's written here is the standard.

The speech key is important. It contains an ID used to track the order of synthesis. It is made up of 2 or at most 3 numbers separated by an underscore. The first number usually isn't importaant, it's the integer client ID that you are known as by the coagulator. If it exists, the second number contains any custom ID you have passed by providing an ID key in your request message. The final number however contains an integer that denotes the fragment number that this speech payload is referencing. When outputting data, you should number or sequence your output based on this second number.

### Writing a speech provider
When a speech provider first connects to a coagulator, it should send a packet in the form:
```{"provider": revision, "voices": ["voice1", "voice2", "etc"]}```
before continuously listening for packets in the form:
```{"voice": "voicename", "text": "text to speak", "id": ID}```
and responding each time with packets such as:
```{"speech": ID, "data": BASE64_ENCODED_WAV}```
where ID is the same as that received in the voice packet's id key.

Voice packets might contain extra parameters like rate and pitch, but your providers should be set up to not require these.

## Disclaimer
This is a tool created with the intention of making it possible for small groups of friends to create tts audio skits and dramas with increased colaberation, or even so that somebody can network all of their local voices together with fewer cables and hastles. By no means is this intended to deprive voice creators of income / hurt them in any way / disrespect their terms of service. Sharing access to voices that disallow such distrobution in their license agreements, particularly beyond small groups of friends, goes against the intended use I had in mind for this project and I expressly disclaim any responsibility for such misuse of the program. Please use this tool respectfully!

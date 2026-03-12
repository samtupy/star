# android

This provider makes all voices installed on any modern Android smartphone or device available to a STAR coagulator.

Unlike most other providers, this one is written in kotlin as a native Android application rather than python.

The provider supports both rate and pitch changes if the requested voices does, they are both multipliers E. <r=2> is double the default rate, <p=2> is double the default pitch etc.

## building

### requirements

You will need the android sdk, jdk 17, and an active internet connection to download gradle files.

There are a few environment variables you need to set before building. These are the `ANDROID_HOME`, and `JAVA_HOME` variables which help locate the Android development tools for anything that needs them.

### actually building the provider

the provider is very easy to build, here are the stepps. 

1. clone the star repo: git clone https://github.com/samtupy/star
2. cd to the provider/android directory within the star repo 
3. if you are on windows, run gradlew assembledebug to build. 

On platforms other than Windows you may need to run `./gradlew` instead of `gradlew`.

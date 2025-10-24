# building the android provider. 
## requirements
you will need the android sdk, jdk 17, and an active internet connection to download gradle files. 
There are a few environment variables you need to set before building. These are the `ANDROID_HOME`, and `JAVA_HOME` variables which help locate the Android development tools for anything that needs them. 
## actually building the provider. 
the provider is very easy to build, here are the stepps. 
1. clone the star repo: git clone https://github.com/samtupy/star
2. cd to the provider/android directory within the star repo 
3. if you are on windows, run gradlew assembledebug to build. 
On platforms other than Windows you may need to run `./gradlew` instead of `gradlew`.
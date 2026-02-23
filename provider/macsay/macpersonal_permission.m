/* Original script from https://apple.stackexchange.com/questions/464984/how-do-i-access-macos-sonoma-personal-voice-from-command-line
 Once xcode is installed, compile with: `gcc -framework AVFoundation -framework Foundation macpersonal_permission.m -o macpersonal_permission`
 After compiling, running ./macpersonal_permission will pop up a permission dialog which will let you grant the terminal and thus STAR authorization to use your MacOS personal voices!
 Be careful doing this though especially on unauthenticated coagulators, as there has been at least one insadent where such a voice has fooled a banking authentication system! https://www.rnz.co.nz/news/national/494083/apple-s-new-voice-replicator-can-bypass-bank-voice-authentication-user-finds
*/

#import <AVFoundation/AVFoundation.h>

int main(){
	[AVSpeechSynthesizer requestPersonalVoiceAuthorizationWithCompletionHandler:^(AVSpeechSynthesisPersonalVoiceAuthorizationStatus status){
		if (status == AVSpeechSynthesisPersonalVoiceAuthorizationStatusUnsupported) printf("personal voices not supported on this machine\n");
		else if (status == AVSpeechSynthesisPersonalVoiceAuthorizationStatusDenied) printf("permission denied\n");
		else if (status == AVSpeechSynthesisPersonalVoiceAuthorizationStatusAuthorized) printf("permission granted, have fun!\n");
		exit(0);
	}];
	[[NSRunLoop currentRunLoop] run];
	return 0;
}

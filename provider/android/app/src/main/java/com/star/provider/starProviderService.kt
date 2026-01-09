package com.star.provider

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Binder
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.*
import okhttp3.Credentials
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.pow
import com.star.provider.R


interface ServiceStateListener {
	fun onStatusUpdate(status: String, isRunning: Boolean)
}

interface ServiceLogListener {
	fun onLogMessage(message: String)
}

private data class CoagulatorConnection(
	val hostUrl: String,
	var webSocket: WebSocket? = null,
	var status: String = "Idle",
	var reconnectAttempts: Int = 0,
	var isManuallyStopped: Boolean = false,
	val handler: Handler = Handler(Looper.getMainLooper()),
	val client: OkHttpClient
)

data class PersistedVoiceConfig(
	val originalName: String,
	val engineName: String,
	var starLabel: String,
	var isEnabled: Boolean
)

data class StarVoiceConfig(
	val originalName: String,
	val engineName: String,
	val androidVoice: Voice,
	var starLabel: String,
	var isEnabled: Boolean = true,
	val systemLocaleTag: String = androidVoice.locale.toLanguageTag(),
	val systemIsNetwork: Boolean = androidVoice.isNetworkConnectionRequired
)

data class DialogVoiceInfo(
	val originalName: String,
	val engineName: String,
	val locale: Locale,
	val isNetwork: Boolean,
	val currentAlias: String,
	val currentIsEnabled: Boolean
)

data class DialogEngineInfo(
	val packageName: String,
	val label: String,
	val isEnabled: Boolean
)

class StarProviderService : Service() {

	private val binder = LocalBinder()
	private val ttsEngines = mutableMapOf<String, TextToSpeech>()
	private val ttsInitializedEngines = mutableSetOf<String>()
	private var ttsDiscoveryInstance: TextToSpeech? = null
	private var allEnginesDiscovered = false
	private val engineLabels = mutableMapOf<String, String>()
	private var allSystemVoices: MutableList<StarVoiceConfig> = mutableListOf()
	private var activeStarVoices: Map<String, StarVoiceConfig> = mapOf()
	private val connections = ConcurrentHashMap<String, CoagulatorConnection>()
	private val synthesisQueue = ConcurrentHashMap<String, SynthesisRequest>()
	private val utteranceContexts = ConcurrentHashMap<String, WebSocket>()
	private val NOTIFICATION_ID = 101
	private val CHANNEL_ID = "StarProviderServiceChannel"
	private var providerNameInternal: String = "AndroidProvider"
	private val providerRevision = 4
	private var currentStatus: String = "Service Idle"
	private var isServiceCurrentlyRunning = false
	private val canceledRequests = ConcurrentHashMap.newKeySet<String>()
	private var isManuallyStopped = false
	private val stateListeners = CopyOnWriteArrayList<ServiceStateListener>()
	private val logListeners = CopyOnWriteArrayList<ServiceLogListener>()
	private lateinit var sharedPreferences: SharedPreferences
	private val VOICE_CONFIG_PREF_KEY = "voice_configurations"
	private val ENGINE_CONFIG_PREF_KEY = "engine_configurations"
	private val LOG_FILE_NAME = "star_provider_service.log"
	private val BACKUP_LOG_FILE_NAME = "star_provider_service.log.1"
	private val MAX_LOG_SIZE_BYTES = 1 * 1024 * 1024
	private var logFile: File? = null

	private data class SynthesisRequest(
		val starRequestId: String,
		val text: String,
		val voiceStarLabel: String,
		val rate: Float,
		val pitch: Float
	)

	inner class LocalBinder : Binder() {
		fun getService(): StarProviderService = this@StarProviderService
		fun registerStateListener(listener: ServiceStateListener) {
			stateListeners.add(listener)
			listener.onStatusUpdate(currentStatus, isServiceCurrentlyRunning)
		}
		fun unregisterStateListener(listener: ServiceStateListener) { stateListeners.remove(listener) }
		fun registerLogListener(listener: ServiceLogListener) { logListeners.add(listener) }
		fun unregisterLogListener(listener: ServiceLogListener) { logListeners.remove(listener) }
	}

	override fun onBind(intent: Intent): IBinder = binder

	override fun onCreate() {
		super.onCreate()
		Log.d("StarProviderService", "onCreate")
		sharedPreferences = getSharedPreferences("StarProviderPrefs", Context.MODE_PRIVATE)
		initializeLogFile()
		logToFile("Service onCreate")
		ttsDiscoveryInstance = TextToSpeech(this) { status ->
			if (status == TextToSpeech.SUCCESS) {
				discoverAllSystemEnginesAndInitialize()
			} else {
				val errorMsg = "TTS Discovery Engine failed to initialize. Status: $status"
				logToFile("CRITICAL: $errorMsg")
				updateStatus(errorMsg, false); stopSelf()
			}
		}
		createNotificationChannel()
	}

	override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
		Log.d("StarProviderService", "onStartCommand received")
		isManuallyStopped = false
		val hostUrls = intent?.getStringArrayListExtra(EXTRA_SERVER_URLS)
		providerNameInternal = intent?.getStringExtra("PROVIDER_NAME") ?: "MyAndroidTTS"

		if (hostUrls.isNullOrEmpty()) {
			val errorMsg = "Error: Server URLs are missing."
			logToFile(errorMsg); updateStatus(errorMsg, false); stopSelf()
			return START_NOT_STICKY
		}
		logToFile("Service starting with ${hostUrls.size} hosts: ${hostUrls.joinToString()}")
		startForegroundService()
		isServiceCurrentlyRunning = true
		updateStatus("Service Starting, Initializing...", true)

		connections.clear()
		hostUrls.forEach { url ->
			val parseableUrl = url.replaceFirst("ws://", "http://", true).replaceFirst("wss://", "https://", true)
			val httpUrl = parseableUrl.toHttpUrlOrNull()
			if (httpUrl == null) {
				logToActivity("Invalid host URL format: $url. Skipping.")
				logToFile("ERROR: Invalid host URL format '$url'. Could not parse.")
				return@forEach
			}
			val user = httpUrl.username
			val pass = httpUrl.password
			val clientBuilder = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).pingInterval(30, TimeUnit.SECONDS)
			if (user.isNotBlank()) {
				val credential = Credentials.basic(user, pass)
				clientBuilder.authenticator { _, response -> response.request.newBuilder().header("Authorization", credential).build() }
			}
			connections[url] = CoagulatorConnection(hostUrl = url, client = clientBuilder.build())
			logToFile("Configured connection for: $url")
		}

		if (connections.isEmpty()) {
			val errorMsg = "No valid host URLs provided."
			logToFile(errorMsg); updateStatus(errorMsg, false); stopSelf()
			return START_NOT_STICKY
		}

		if (isTtsReady()) {
			connections.keys.forEach { connectWebSocket(it) }
		} else {
			logToFile("TTS not ready, connections will be attempted after initialization.")
		}
		return START_STICKY
	}

	private fun startForegroundService() {
		val notificationIntent = Intent(this, MainActivity::class.java)
		val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT else PendingIntent.FLAG_UPDATE_CURRENT
		val pendingIntent = PendingIntent.getActivity(this, 0, notificationIntent, pendingIntentFlags)
		val notification = NotificationCompat.Builder(this, CHANNEL_ID)
			.setContentTitle("STAR Provider Active").setContentText("Initializing...")
			.setSmallIcon(R.drawable.ic_stat_name).setContentIntent(pendingIntent)
			.setOngoing(true).build()
		startForeground(NOTIFICATION_ID, notification)
	}

	private fun discoverAllSystemEnginesAndInitialize() {
		logToFile("Starting initial discovery of all system TTS engines...")
		val allSystemEngineInfos = ttsDiscoveryInstance?.engines ?: run {
			updateStatus("Error: Could not query TTS engines.", false); stopSelf(); return
		}
		if (allSystemEngineInfos.isEmpty()) {
			updateStatus("No TTS engines found on this device.", false); stopSelf(); return
		}
		engineLabels.clear()
		allSystemEngineInfos.forEach { engineInfo -> engineLabels[engineInfo.name] = engineInfo.label }
		allEnginesDiscovered = true
		logToFile("Discovered ${engineLabels.size} total engines: ${engineLabels.values.joinToString()}")
		initializeEnabledEngines()
	}

	private fun initializeEnabledEngines(onComplete: (() -> Unit)? = null) {
		logToFile("Initializing enabled engines...")
		val enabledEngineConfigs = loadEngineConfigurations()
		val enginesToInitialize = engineLabels.filter { (packageName, _) -> enabledEngineConfigs.getOrDefault(packageName, true) }
		logToFile("Engines to be initialized: ${enginesToInitialize.values.joinToString()}")

		if (enginesToInitialize.isEmpty()) {
			logToActivity("No engines are enabled.")
			populateAvailableVoices()
			onComplete?.invoke()
			return
		}

		val initializationCounter = AtomicInteger(enginesToInitialize.size)
		enginesToInitialize.forEach { (enginePackageName, engineLabel) ->
			try {
				val ttsInstance = TextToSpeech(this, { status ->
					if (status == TextToSpeech.SUCCESS) {
						ttsInitializedEngines.add(enginePackageName)
						ttsEngines[enginePackageName]?.setOnUtteranceProgressListener(StarUtteranceListener())
						logToFile("TTS Engine initialized successfully: $engineLabel")
					} else {
						logToFile("TTS Engine failed to initialize: $engineLabel, Status: $status")
					}
					if (initializationCounter.decrementAndGet() == 0) {
						logToFile("All requested engines have finished initialization process.")
						populateAvailableVoices()
						onComplete?.invoke()
					}
				}, enginePackageName)
				ttsEngines[enginePackageName] = ttsInstance
			} catch (e: Exception) {
				logToFile("Failed to instantiate TTS engine $engineLabel: ${e.message}")
				if (initializationCounter.decrementAndGet() == 0) {
					logToFile("All requested engines have finished initialization process (with errors).")
					populateAvailableVoices()
					onComplete?.invoke()
				}
			}
		}
	}

	fun saveAndReloadEngineConfigs(newConfigs: Map<String, Boolean>) {
		sharedPreferences.edit().putString(ENGINE_CONFIG_PREF_KEY, JSONObject(newConfigs as Map<*, *>).toString()).apply()
		logToFile("Saved updated engine configurations. Performing full state refresh.")
		logToActivity("Applying new engine configuration...")

		val onRefreshComplete = {
			logToActivity("Engine refresh complete. Repopulating voice list from active engines.")
			populateAvailableVoices()

			logToActivity("Forcing reconnection to servers to apply new engine configuration.")
			val hostsToReconnect = connections.keys.toList()
			hostsToReconnect.forEach { hostUrl ->
				connections[hostUrl]?.let { conn ->
					conn.webSocket?.close(1000, "Re-registering new engine configuration")
					conn.webSocket = null
					conn.handler.removeCallbacksAndMessages(null)
					conn.reconnectAttempts = 0
					logToFile("Force-reconnecting to $hostUrl to apply engine changes.")
					connectWebSocket(hostUrl)
				}
			}
		}

		logToFile("Shutting down all current TTS engines before re-initialization.")
		ttsEngines.values.toList().forEach { engine ->
			try {
				engine.shutdown()
			} catch (e: Exception) {
				logToFile("Error during engine shutdown: ${e.message}")
			}
		}
		ttsEngines.clear()
		ttsInitializedEngines.clear()
		logToFile("All running engines shut down and active state cleared.")

		logToFile("Starting re-initialization of enabled engines...")
		initializeEnabledEngines(onComplete = onRefreshComplete)
	}

	fun getSystemEnginesForConfiguration(): List<DialogEngineInfo> {
		if (!allEnginesDiscovered) return emptyList()
		val persistedConfigs = loadEngineConfigurations()
		return engineLabels.map { (packageName, label) ->
			DialogEngineInfo(packageName, label, persistedConfigs.getOrDefault(packageName, true))
		}.sortedBy { it.label }
	}

	private fun loadEngineConfigurations(): Map<String, Boolean> {
		val jsonString = sharedPreferences.getString(ENGINE_CONFIG_PREF_KEY, null)
		return if (jsonString != null) {
			try {
				val json = JSONObject(jsonString)
				json.keys().asSequence().associateWith { key -> json.getBoolean(key) }
			} catch (e: Exception) {
				Log.e("StarProviderService", "Error parsing engine configurations", e); emptyMap()
			}
		} else { emptyMap() }
	}

	fun getSystemVoicesForConfiguration(): List<DialogVoiceInfo> {
		if (!isTtsReady() && ttsInitializedEngines.isEmpty()) return emptyList()
		val persistedConfigs = loadVoiceConfigurations().associateBy { "${it.engineName}:${it.originalName}" }
		return ttsInitializedEngines.flatMap { engineName ->
			val tts = ttsEngines[engineName] ?: return@flatMap emptyList()
			try {
				tts.voices?.mapNotNull { voice ->
					val configKey = "$engineName:${voice.name}"
					val persisted = persistedConfigs[configKey]
					val shortEngineName = getShortEngineName(engineName)
					val defaultAlias = "${shortEngineName}_${voice.name}".replace(Regex("[^a-zA-Z0-9_-]" ), "_")
					DialogVoiceInfo(voice.name, engineName, voice.locale, voice.isNetworkConnectionRequired,
						persisted?.starLabel ?: defaultAlias, persisted?.isEnabled ?: true)
				} ?: emptyList()
			} catch (e: Exception) {
				Log.e("StarProviderService", "Error getting voices for engine $engineName: ${e.message}", e); emptyList()
			}
		}
	}

	fun savePersistedVoiceConfigs(configs: List<PersistedVoiceConfig>) {
		sharedPreferences.edit().putString(VOICE_CONFIG_PREF_KEY, convertPersistedVoiceConfigListToJson(configs)).apply()
		logToFile("Saved updated voice configurations from MainActivity.")
		logToActivity("Applying new voice settings...")
		
		populateAvailableVoices()
		
		logToActivity("Forcing reconnection to servers to apply new voice list.")
		val hostsToReconnect = connections.keys.toList()
		hostsToReconnect.forEach { hostUrl ->
			connections[hostUrl]?.let { conn ->
				conn.webSocket?.close(1000, "Re-registering new voice configuration")
				conn.webSocket = null
				
				conn.handler.removeCallbacksAndMessages(null)
				
				conn.reconnectAttempts = 0
				
				logToFile("Force-reconnecting to $hostUrl to apply voice changes.")
				connectWebSocket(hostUrl)
			}
		}
	}

	private fun loadVoiceConfigurations(): List<PersistedVoiceConfig> {
		val jsonString = sharedPreferences.getString(VOICE_CONFIG_PREF_KEY, null)
		return if (jsonString != null) {
			try { parsePersistedVoiceConfigListFromJson(jsonString)
			} catch (e: Exception) { Log.e("StarProviderService", "Error parsing voice configurations from JSON", e); emptyList() }
		} else { emptyList() }
	}

	private fun convertPersistedVoiceConfigListToJson(configs: List<PersistedVoiceConfig>): String {
		val jsonArray = JSONArray()
		configs.forEach { config ->
			val jsonObj = JSONObject()
			jsonObj.put("originalName", config.originalName); jsonObj.put("engineName", config.engineName)
			jsonObj.put("starLabel", config.starLabel); jsonObj.put("isEnabled", config.isEnabled)
			jsonArray.put(jsonObj)
		}
		return jsonArray.toString()
	}

	private fun parsePersistedVoiceConfigListFromJson(jsonString: String): List<PersistedVoiceConfig> {
		val configs = mutableListOf<PersistedVoiceConfig>()
		try {
			val jsonArray = JSONArray(jsonString)
			for (i in 0 until jsonArray.length()) {
				val jsonObj = jsonArray.getJSONObject(i)
				configs.add(PersistedVoiceConfig(
					originalName = jsonObj.getString("originalName"), engineName = jsonObj.getString("engineName"),
					starLabel = jsonObj.getString("starLabel"), isEnabled = jsonObj.getBoolean("isEnabled")
				))
			}
		} catch (e: JSONException) { Log.e("StarProviderService", "Manual JSON parsing error for voice configs: ${e.message}", e) }
		return configs
	}

	private fun getShortEngineName(engineName: String): String {
		return when {
			engineName.contains("google") -> "google"
			engineName.contains("rhvoice") -> "rhvoice"
			engineName.contains("espeak") -> "espeak"
			engineName.contains("dectalk") -> "dectalk"
			engineName.contains("samsung") -> "samsung"
			else -> engineName.split(".").lastOrNull() ?: "eng"
		}
	}

	private fun populateAvailableVoices() {
		allSystemVoices.clear()
		val persistedVoiceConfigs = loadVoiceConfigurations().associateBy { "${it.engineName}:${it.originalName}" }
		var voiceDetailsLog = "Populating available voices based on active engines...\n"
		val activeEngines = ttsInitializedEngines.toList()
		voiceDetailsLog += "Active initialized engines: ${activeEngines.joinToString { engineLabels[it] ?: it }}\n"
		activeEngines.forEach { engineName ->
			val tts = ttsEngines[engineName] ?: return@forEach
			val engineLabel = engineLabels[engineName] ?: "Unknown"
			try {
				tts.voices?.forEach { voice ->
					val configKey = "$engineName:${voice.name}"
					val persistedConfig = persistedVoiceConfigs[configKey]
					val shortEngineName = getShortEngineName(engineName)
					val defaultStarLabel = "${shortEngineName}_${voice.name}".replace(Regex("[^a-zA-Z0-9_-]" ), "_")
					val starLabel = persistedConfig?.starLabel ?: defaultStarLabel
					val isEnabled = persistedConfig?.isEnabled ?: true
					val voiceConfig = StarVoiceConfig(originalName = voice.name, engineName = engineName, androidVoice = voice, starLabel = starLabel, isEnabled = isEnabled)
					allSystemVoices.add(voiceConfig)
					voiceDetailsLog += "  Found voice: ${voice.name} (Engine: $engineLabel), STAR Label: ${voiceConfig.starLabel}, Enabled: ${voiceConfig.isEnabled}\n"
				}
			} catch (e: Exception) {
				voiceDetailsLog += "  Error populating voices for $engineName: ${e.message}\n"
			}
		}
		val finalActiveVoices = mutableMapOf<String, StarVoiceConfig>()
		val usedLabels = mutableSetOf<String>()
		allSystemVoices.filter { it.isEnabled }.forEach { config ->
			var currentLabel = config.starLabel; var counter = 1
			while(usedLabels.contains(currentLabel)) { currentLabel = "${config.starLabel}_${counter++}" }
			usedLabels.add(currentLabel)
			finalActiveVoices[currentLabel] = config.copy(starLabel = currentLabel)
		}
		activeStarVoices = finalActiveVoices
		logToFile(voiceDetailsLog.trim())
		if (activeStarVoices.isEmpty()) {
			logToActivity("Warning: No active TTS voices found or configured.")
		}
		updateCombinedStatus()
	}

	private fun connectWebSocket(hostUrl: String) {
		val connection = connections[hostUrl]
		if (connection == null) { logToFile("Error: Attempted to connect to an unconfigured host: $hostUrl"); return }
		if (connection.webSocket != null) { logToActivity("WebSocket for $hostUrl already connected or connecting."); return }
		val connectMsg = "Attempting to connect to: $hostUrl (Attempt: ${connection.reconnectAttempts + 1})"
		logToFile(connectMsg)
		val request = Request.Builder().url(hostUrl).build()
		connection.client.newWebSocket(request, StarWebSocketListener(hostUrl))
		connection.status = "Connecting... (Attempt ${connection.reconnectAttempts + 1})"
		updateCombinedStatus()
	}

	private fun scheduleReconnect(hostUrl: String) {
		val connection = connections[hostUrl] ?: return
		val maxReconnectAttempts = 10
		val initialReconnectDelayMs = 1000L
		if (connection.isManuallyStopped || connection.reconnectAttempts >= maxReconnectAttempts) {
			logToFile("Max reconnects for $hostUrl or manually stopped. Giving up.")
			connection.status = "Disconnected (Max retries)"; updateCombinedStatus(); return
		}
		val delay = (initialReconnectDelayMs * 2.0.pow(connection.reconnectAttempts.toDouble())).toLong()
		connection.reconnectAttempts++
		logToFile("Scheduling reconnect for $hostUrl in ${delay}ms.")
		logToActivity("Connection to $hostUrl lost. Reconnecting in ${delay/1000}s...")
		connection.status = "Reconnecting (Attempt ${connection.reconnectAttempts})..."
		updateCombinedStatus()
		connection.handler.postDelayed({
			if (!connection.isManuallyStopped) {
				logToFile("Executing reconnect for $hostUrl.")
				connectWebSocket(hostUrl)
			} else {
				logToFile("Reconnect for $hostUrl cancelled.")
			}
		}, delay)
	}

	private fun registerWithCoagulator(webSocket: WebSocket) {
		if (!isTtsReady() && activeStarVoices.isEmpty()) {
			logToActivity("TTS not fully ready, but sending available voices (${activeStarVoices.size})")
		}
		val registrationPayload = JSONObject().apply {
			put("provider", providerRevision)
			put("provider_name", providerNameInternal)
			put("voices", JSONArray(activeStarVoices.keys.toList()))
		}.toString()
		logToFile("TX Registration to ${webSocket.request().url}: $registrationPayload")
		val sent = webSocket.send(registrationPayload)
		if (sent) { logToActivity("Registration sent to ${webSocket.request().url.host}.") }
		else { logToActivity("Failed to send registration to ${webSocket.request().url.host}.") }
	}

	private inner class StarWebSocketListener(private val hostUrl: String) : WebSocketListener() {
		override fun onOpen(webSocket: WebSocket, response: Response) {
			val connection = connections[hostUrl] ?: return
			connection.webSocket = webSocket; connection.reconnectAttempts = 0; connection.status = "Connected"
			val msg = "WebSocket Connected to $hostUrl"
			Log.i("StarProviderService", msg); logToActivity(msg); updateCombinedStatus(); registerWithCoagulator(webSocket)
		}
		override fun onMessage(webSocket: WebSocket, text: String) {
			Log.d("StarProviderService", "RX Text from ${webSocket.request().url.host}: $text"); logToActivity("RX: $text")
			try {
				val json = JSONObject(text)
				if (json.has("abort")) {
					val requestIdToCancel = json.optString("abort"); if (requestIdToCancel.isNotEmpty()) {
						canceledRequests.add(requestIdToCancel); logToActivity("Abort request for ID: $requestIdToCancel.")
					}; return
				}
				if (!json.has("voice") || !json.has("text") || !json.has("id")) {
					logToActivity("Invalid request (missing fields): $text"); return
				}
				handleSynthesisRequest(json.getString("voice"), json.getString("text"), json.getString("id"),
					json.optDouble("rate", 1.0).toFloat(), json.optDouble("pitch", 1.0).toFloat(), webSocket)
			} catch (e: JSONException) { logToActivity("Error parsing JSON from server: ${e.message}") }
		}
		override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
			val msg = "WebSocket Closing for $hostUrl: $code / $reason"
			Log.i("StarProviderService", msg); logToActivity(msg); cleanupWebSocket(hostUrl)
			if (code != 1000 && !(connections[hostUrl]?.isManuallyStopped ?: false)) { scheduleReconnect(hostUrl)
			} else { connections[hostUrl]?.status = "Disconnected"; updateCombinedStatus() }
		}
		override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
			val msg = "WebSocket Failure for $hostUrl: ${t.message}"
			Log.e("StarProviderService", msg, t); logToActivity(msg); cleanupWebSocket(hostUrl)
			if (!(connections[hostUrl]?.isManuallyStopped ?: false)) { scheduleReconnect(hostUrl)
			} else { connections[hostUrl]?.status = "Disconnected (Failure)"; updateCombinedStatus() }
		}
		override fun onMessage(webSocket: WebSocket, bytes: ByteString) { val msg = "RX Binary from ${webSocket.request().url.host}: ${bytes.hex()}"; Log.d("StarProviderService", msg); logToActivity(msg) }
	}

	private fun cleanupWebSocket(hostUrl: String) {
		logToFile("Cleaning up WebSocket for $hostUrl.")
		val connection = connections[hostUrl]; connection?.webSocket?.close(1000, "Client closing"); connection?.webSocket = null; updateCombinedStatus()
	}

	private fun handleSynthesisRequest(voiceStarLabel: String, textToSpeak: String, starRequestId: String, rate: Float, pitch: Float, sourceSocket: WebSocket) {
		logToFile("Handling synthesis ID: $starRequestId from ${sourceSocket.request().url.host}, Voice: $voiceStarLabel, Text: \"${textToSpeak.take(50)}...\"")
		if (canceledRequests.contains(starRequestId)) {
			canceledRequests.remove(starRequestId); logToActivity("Synthesis for ID $starRequestId canceled by client before starting.")
			sendError(starRequestId, "Request canceled by client.", sourceSocket); return
		}
		if (!isTtsReady()) { sendError(starRequestId, "TTS not ready on Android provider for request $starRequestId.", sourceSocket); return }
		val voiceConfig = activeStarVoices[voiceStarLabel]
		if (voiceConfig == null) {
			val errorMsg = "Voice '$voiceStarLabel' not found or not active. Active: ${activeStarVoices.keys.joinToString()}"
			sendError(starRequestId, errorMsg, sourceSocket); logToActivity(errorMsg); return
		}
		val tts = ttsEngines[voiceConfig.engineName]
		if (tts == null) {
			val errorMsg = "TTS engine '${voiceConfig.engineName}' for voice '$voiceStarLabel' is not available or failed to initialize."
			sendError(starRequestId, errorMsg, sourceSocket); logToActivity(errorMsg); return
		}
		val utteranceId = UUID.randomUUID().toString()
		synthesisQueue[utteranceId] = SynthesisRequest(starRequestId, textToSpeak, voiceStarLabel, rate, pitch)
		utteranceContexts[utteranceId] = sourceSocket
		tts.voice = voiceConfig.androidVoice; tts.setSpeechRate(rate.coerceIn(0.1f, 4.0f)); tts.setPitch(pitch.coerceIn(0.1f, 4.0f))
		val tempAudioFile = File(cacheDir, "$utteranceId.wav")
		logToActivity("Synthesizing for $starRequestId (utt: $utteranceId) using Engine: ${engineLabels[voiceConfig.engineName] ?: "Unknown"}, Voice: ${voiceConfig.androidVoice.name}")
		val result = tts.synthesizeToFile(textToSpeak, Bundle(), tempAudioFile, utteranceId)
		if (result != TextToSpeech.SUCCESS) {
			val errorMsg = "TTS synthesizeToFile failed for $utteranceId (STAR ID: $starRequestId). Code: $result"
			Log.e("StarProviderService", errorMsg); logToFile(errorMsg)
			synthesisQueue.remove(utteranceId); utteranceContexts.remove(utteranceId)
			sendError(starRequestId, "Android TTS synthesis command failed (code: $result).", sourceSocket)
			tempAudioFile.delete()
		}
	}

	private inner class StarUtteranceListener : UtteranceProgressListener() {
		override fun onStart(utteranceId: String?) {
			Log.d("TTSListener", "Utterance started: $utteranceId")
			synthesisQueue[utteranceId]?.let { logToActivity("TTS synthesis started for STAR ID: ${it.starRequestId} (Utt: $utteranceId)") }
		}
		override fun onDone(utteranceId: String?) {
			Log.d("TTSListener", "Utterance done: $utteranceId")
			val requestDetails = synthesisQueue.remove(utteranceId)
			val sourceSocket = utteranceContexts.remove(utteranceId)
			if (utteranceId != null && requestDetails != null && sourceSocket != null) {
				if (canceledRequests.contains(requestDetails.starRequestId)) {
					canceledRequests.remove(requestDetails.starRequestId)
					logToActivity("Synthesis for ID ${requestDetails.starRequestId} completed but was canceled. Audio not sent.")
					File(cacheDir, "$utteranceId.wav").delete(); return
				}
				val audioFile = File(cacheDir, "$utteranceId.wav")
				if (audioFile.exists() && audioFile.length() > 0) {
					logToActivity("TTS synthesis done for ${requestDetails.starRequestId}, sending audio (${audioFile.length()} bytes).")
					sendAudioData(requestDetails.starRequestId, audioFile, sourceSocket)
				} else {
					sendError(requestDetails.starRequestId, "Synthesized audio file not found or was empty.", sourceSocket)
				}
				audioFile.delete()
			}
		}
		override fun onError(utteranceId: String?, errorCode: Int) {
			val errorDetail = ttsErrorToString(errorCode)
			Log.e("TTSListener", "TTSListener: onError for $utteranceId, code: $errorCode ($errorDetail)")
			handleTtsError(utteranceId, errorDetail)
		}
		private fun handleTtsError(utteranceId: String?, errorMessage: String) {
			val requestDetails = synthesisQueue.remove(utteranceId)
			val sourceSocket = utteranceContexts.remove(utteranceId)
			if (utteranceId != null && requestDetails != null && sourceSocket != null) {
				if (!canceledRequests.remove(requestDetails.starRequestId)) {
					val detailedError = "Android TTS Error for ${requestDetails.starRequestId}: $errorMessage"
					sendError(requestDetails.starRequestId, detailedError, sourceSocket)
				}
			}
			File(cacheDir, "$utteranceId.wav").delete()
		}
		@Deprecated("deprecated", replaceWith = ReplaceWith("onError(utteranceId, errorCode)"))
		override fun onError(utteranceId: String?) { onError(utteranceId, -1) }
		private fun ttsErrorToString(errorCode: Int): String = when (errorCode) {
			TextToSpeech.ERROR_SYNTHESIS -> "Synthesis error"; TextToSpeech.ERROR_SERVICE -> "Service error (TTS engine)"
			TextToSpeech.ERROR_OUTPUT -> "Output error"; TextToSpeech.ERROR_NETWORK -> "Network error"
			TextToSpeech.ERROR_NETWORK_TIMEOUT -> "Network timeout"; TextToSpeech.ERROR_INVALID_REQUEST -> "Invalid request"
			TextToSpeech.ERROR_NOT_INSTALLED_YET -> "TTS data not installed yet"; else -> "Unknown TTS error ($errorCode)"
		}
	}

	private fun sendAudioData(starRequestId: String, audioFile: File, destinationSocket: WebSocket) {
		val audioBytes = audioFile.readBytes()
		val metadataJsonString = JSONObject().apply { put("id", starRequestId); put("extension", "wav") }.toString()
		val metadataBytes = metadataJsonString.toByteArray(Charsets.UTF_8)
		val metadataLength = metadataBytes.size.toShort()
		val packetBuffer = ByteBuffer.allocate(2 + metadataBytes.size + audioBytes.size)
		packetBuffer.order(ByteOrder.LITTLE_ENDIAN); packetBuffer.putShort(metadataLength); packetBuffer.put(metadataBytes); packetBuffer.put(audioBytes)
		val combinedPacket = packetBuffer.array().toByteString(0, packetBuffer.position())
		val sent = destinationSocket.send(combinedPacket)
		if (sent) logToActivity("Sent audio for $starRequestId to ${destinationSocket.request().url.host}")
		else logToActivity("Failed to send audio packet for $starRequestId to ${destinationSocket.request().url.host}")
	}

	private fun sendError(starRequestId: String, errorMessage: String, destinationSocket: WebSocket) {
		val errorPayload = JSONObject().apply {
			put("provider", providerRevision); put("id", starRequestId)
			put("status", errorMessage.take(200)); put("abort", true)
		}.toString()
		logToFile("TX Error for $starRequestId to ${destinationSocket.request().url.host}: $errorMessage")
		destinationSocket.send(errorPayload)
	}

	private fun updateCombinedStatus() {
		val connectedCount = connections.values.count { it.webSocket != null && it.status == "Connected" }
		val totalCount = connections.size
		val isAnyConnecting = connections.values.any { it.status.contains("Connecting") || it.status.contains("Reconnecting") }
		val summary = if (totalCount > 0) "Connected to $connectedCount of $totalCount hosts. Voices: ${activeStarVoices.size}"
		else "No hosts configured. Voices: ${activeStarVoices.size}"
		val isRunning = connectedCount > 0 || isAnyConnecting
		updateStatus(summary, isRunning)
	}

	private fun updateStatus(newStatus: String, isRunning: Boolean) {
		currentStatus = newStatus; isServiceCurrentlyRunning = isRunning
		Log.i("StarProviderService", "Status Update: $newStatus, IsRunning: $isRunning")
		updateNotification(newStatus); stateListeners.forEach { it.onStatusUpdate(newStatus, isRunning) }
	}

	internal fun stopServiceInternal() {
		isManuallyStopped = true
		logToActivity("Service stop requested by MainActivity.")
		connections.values.forEach { it.isManuallyStopped = true; it.handler.removeCallbacksAndMessages(null); cleanupWebSocket(it.hostUrl) }
		connections.clear(); ttsEngines.values.forEach { try { it.stop() } catch (e: Exception) { /* ignore */ } }
		stopForeground(STOP_FOREGROUND_REMOVE); stopSelf()
	}

	override fun onDestroy() {
		super.onDestroy()
		isManuallyStopped = true; updateStatus("Service Stopped", false)
		logToFile("Service onDestroy. Cleaning up all resources.")
		ttsDiscoveryInstance?.shutdown()
		ttsEngines.values.forEach { try { it.shutdown() } catch(e: Exception) { /* ignore */ } }
		ttsEngines.clear(); ttsInitializedEngines.clear()
		connections.values.forEach { it.handler.removeCallbacksAndMessages(null) }
		connections.clear()
		logToFile("--- Log session ended: ${getCurrentTimestamp()} ---", false)
		stateListeners.clear(); logListeners.clear()
	}

	companion object { const val EXTRA_SERVER_URLS = "com.star.provider.EXTRA_SERVER_URLS" }
	private fun isTtsReady(): Boolean = ttsInitializedEngines.isNotEmpty() || activeStarVoices.isNotEmpty()
	fun isRunning(): Boolean = isServiceCurrentlyRunning
	fun requestCurrentStatus() { stateListeners.forEach { it.onStatusUpdate(currentStatus, isServiceCurrentlyRunning) } }

	private fun createNotificationChannel() {
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
			val serviceChannel = NotificationChannel(CHANNEL_ID, "STAR Provider Service", NotificationManager.IMPORTANCE_LOW)
			getSystemService(NotificationManager::class.java)?.createNotificationChannel(serviceChannel);
		}
	}

	private fun updateNotification(message: String) {
		val notificationIntent = Intent(this, MainActivity::class.java)
		val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT else PendingIntent.FLAG_UPDATE_CURRENT
		val pendingIntent = PendingIntent.getActivity(this, 0, notificationIntent, pendingIntentFlags)
		val notification = NotificationCompat.Builder(this, CHANNEL_ID)
			.setContentTitle("STAR Provider").setContentText(message)
			.setSmallIcon(R.drawable.ic_stat_name).setContentIntent(pendingIntent)
			.setOngoing(true).setOnlyAlertOnce(true).build()
		(getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify(NOTIFICATION_ID, notification)
	}

	private fun logToActivity(message: String) { Log.d("StarProviderServiceLog", message); logToFile(message); logListeners.forEach { it.onLogMessage(message) } }

	private fun initializeLogFile() {
		try {
			val logsDir = File(getExternalFilesDir(null), "logs"); if (!logsDir.exists()) logsDir.mkdirs()
			logFile = File(logsDir, LOG_FILE_NAME); if (!logFile!!.exists()) { logFile!!.createNewFile() }
			logToFile("--- Log session started: ${getCurrentTimestamp()} ---", false)
		} catch (e: Exception) { Log.e("StarProviderService", "Error initializing log file", e); logFile = null }
	}

	private fun getCurrentTimestamp(): String = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault()).format(Date())

	private fun logToFile(message: String, includeTimestamp: Boolean = true) {
		if (logFile == null) initializeLogFile()
		logFile?.let { file ->
			try {
				if (file.length() > MAX_LOG_SIZE_BYTES) {
					val backupFile = File(file.parentFile, BACKUP_LOG_FILE_NAME); if (backupFile.exists()) backupFile.delete()
					file.renameTo(backupFile); if (file.createNewFile()) {
						FileOutputStream(file, true).bufferedWriter().use { it.append("${getCurrentTimestamp()} - Log file rotated.\n") }
					}
				}
				FileOutputStream(file, true).bufferedWriter().use { it.append(if(includeTimestamp) "${getCurrentTimestamp()} - $message\n" else "$message\n") }
			} catch (e: IOException) { Log.e("StarProviderService", "Error writing to log file", e) }
		}
	}
}

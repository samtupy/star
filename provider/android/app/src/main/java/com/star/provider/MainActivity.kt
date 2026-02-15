package com.star.provider

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.SharedPreferences
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.CollectionInfo
import androidx.compose.ui.semantics.CollectionItemInfo
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.ScrollAxisRange
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.collectionInfo
import androidx.compose.ui.semantics.collectionItemInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.horizontalScrollAxisRange
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.verticalScrollAxisRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.core.content.ContextCompat
import com.star.provider.ui.theme.StarProviderTheme
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale
import com.star.provider.ServiceStateListener
import com.star.provider.ServiceLogListener
import com.star.provider.PersistedVoiceConfig
import com.star.provider.DialogVoiceInfo
import com.star.provider.DialogEngineInfo

const val PREFS_NAME = "StarProviderPrefs"
const val KEY_SERVER_URLS = "server_urls"
const val KEY_PROVIDER_NAME = "provider_name"

class MainActivity : ComponentActivity(), ServiceStateListener, ServiceLogListener {

	private var starProviderService: StarProviderService? = null
	private var serviceBinder: StarProviderService.LocalBinder? = null
	private var isBound = false
	private lateinit var sharedPreferences: SharedPreferences

	private val _serverUrls = mutableStateListOf<String>()
	private val _providerName = mutableStateOf("MyAndroidTTS")
	private val _currentStatus = mutableStateOf("Status: Disconnected")
	private val _logMessages = mutableStateOf("Logs will appear here...")
	private val _isServiceRunningState = mutableStateOf(false)
	private val _showVoiceConfigDialog = mutableStateOf(false)
	private val _showEngineConfigDialog = mutableStateOf(false)

	private val connection = object : ServiceConnection {
		override fun onServiceConnected(className: ComponentName, service: IBinder) {
			serviceBinder = service as StarProviderService.LocalBinder
			starProviderService = serviceBinder?.getService()
			isBound = true
			Log.d("MainActivity", "Service connected")
			serviceBinder?.registerStateListener(this@MainActivity)
			serviceBinder?.registerLogListener(this@MainActivity)
			starProviderService?.requestCurrentStatus()
		}

		override fun onServiceDisconnected(arg0: ComponentName) {
			if (isBound) {
				serviceBinder?.unregisterStateListener(this@MainActivity)
				serviceBinder?.unregisterLogListener(this@MainActivity)
				isBound = false
				serviceBinder = null
				starProviderService = null
				Log.d("MainActivity", "Service disconnected")
			}
			_currentStatus.value = "Status: Service Unbound"
			_isServiceRunningState.value = false
		}
	}

	private val requestPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted: Boolean ->
		if (isGranted) { Log.i("MainActivity", "Notification permission granted.") }
		else { Log.w("MainActivity", "Notification permission denied.") }
	}

	override fun onStatusUpdate(status: String, isRunning: Boolean) { CoroutineScope(Dispatchers.Main).launch { _currentStatus.value = status; _isServiceRunningState.value = isRunning } }
	override fun onLogMessage(message: String) { CoroutineScope(Dispatchers.Main).launch { _logMessages.value = (_logMessages.value + "\n" + message).takeLast(2000) } }

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		sharedPreferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

		val savedUrls = sharedPreferences.getStringSet(KEY_SERVER_URLS, null)
		if (savedUrls.isNullOrEmpty()) {
			_serverUrls.add("ws://localhost:8765")
		} else {
			_serverUrls.addAll(savedUrls)
		}

		_providerName.value = sharedPreferences.getString(KEY_PROVIDER_NAME, "MyAndroidTTS") ?: "MyAndroidTTS"

		setContent {
			StarProviderTheme {
				StarProviderScreen(
					serverUrls = _serverUrls,
					onAddServerUrl = { url ->
						val trimmedUrl = url.trim()
						if (trimmedUrl.isNotBlank() && !_serverUrls.contains(trimmedUrl)) {
							_serverUrls.add(trimmedUrl)
							saveUrls()
						}
					},
				onRemoveServerUrl = { url -> _serverUrls.remove(url); saveUrls() },
					providerName = _providerName.value,
					onProviderNameChange = { _providerName.value = it; sharedPreferences.edit().putString(KEY_PROVIDER_NAME, it).apply() },
					currentStatus = _currentStatus.value,
					logMessages = _logMessages.value,
					isServiceRunning = _isServiceRunningState.value,
					onStartStopClick = { toggleService() },
					onConfigureVoicesClick = { _showVoiceConfigDialog.value = true },
					onConfigureEnginesClick = { _showEngineConfigDialog.value = true }
				)
				if (_showVoiceConfigDialog.value) {
					VoiceConfigurationDialog(onDismiss = { _showVoiceConfigDialog.value = false }, starProviderService = starProviderService)
				}
				if (_showEngineConfigDialog.value) {
					EngineConfigurationDialog(onDismiss = { _showEngineConfigDialog.value = false }, starProviderService = starProviderService)
				}
			}
		}
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) { requestNotificationPermission() }
	}

	private fun saveUrls() {
		sharedPreferences.edit().putStringSet(KEY_SERVER_URLS, _serverUrls.toSet()).apply()
	}

	override fun onStart() {
		super.onStart()
		Intent(this, StarProviderService::class.java).also { intent ->
			try {
				bindService(intent, connection, Context.BIND_AUTO_CREATE)
			} catch (e: SecurityException) {
				Log.e("MainActivity", "Failed to bind to service", e)
				_currentStatus.value = "Error: Cannot bind to service."
			}
		}
	}

	override fun onStop() {
		super.onStop()
		if (isBound) {
			serviceBinder?.unregisterStateListener(this)
			serviceBinder?.unregisterLogListener(this)
			unbindService(connection)
			isBound = false
		}
	}

	private fun requestNotificationPermission() {
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
			requestPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
		}
	}

	private fun startProviderService() {
		saveUrls()
		sharedPreferences.edit().putString(KEY_PROVIDER_NAME, _providerName.value).apply()

		val serviceIntent = Intent(this, StarProviderService::class.java).apply {
			putStringArrayListExtra(StarProviderService.EXTRA_SERVER_URLS, ArrayList(_serverUrls))
			putExtra("PROVIDER_NAME", _providerName.value)
		}
		try {
			ContextCompat.startForegroundService(this, serviceIntent)
			if (!isBound) {
				bindService(serviceIntent, connection, Context.BIND_AUTO_CREATE)
			}
		} catch (e: Exception) {
			Log.e("MainActivity", "Error starting service", e)
			_currentStatus.value = "Error: Could not start service. ${e.message}"
			if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && e is SecurityException) {
				_currentStatus.value = "Error: FG Service start restricted by OS."
			}
		}
	}

	private fun stopProviderService() {
		starProviderService?.stopServiceInternal() ?: run {
			val serviceIntent = Intent(this, StarProviderService::class.java)
			try {
				stopService(serviceIntent)
				Log.i("MainActivity", "stopService() called directly.")
			} catch (e: Exception) {
				Log.e("MainActivity", "Error calling stopService()", e)
			}
		}
		if (!isBound) {
			_currentStatus.value = "Status: Disconnected"
			_isServiceRunningState.value = false
		}
	}

	private fun toggleService() {
		if (_isServiceRunningState.value) {
			stopProviderService()
		} else {
			startProviderService()
		}
	}
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StarProviderScreen(
	serverUrls: List<String>, onAddServerUrl: (String) -> Unit, onRemoveServerUrl: (String) -> Unit,
	providerName: String, onProviderNameChange: (String) -> Unit,
	currentStatus: String, logMessages: String, isServiceRunning: Boolean,
	onStartStopClick: () -> Unit, onConfigureVoicesClick: () -> Unit, onConfigureEnginesClick: () -> Unit
) {
	val logScrollState = rememberScrollState()

	Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
		LazyColumn(
			modifier = Modifier
					.fillMaxSize()
					.padding(16.dp),
			horizontalAlignment = Alignment.CenterHorizontally
		) {
			item { Text("STAR Android TTS Provider", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(bottom = 16.dp)) }

			item { Text("Coagulator Hosts", style = MaterialTheme.typography.titleMedium, modifier = Modifier.fillMaxWidth())
				Spacer(Modifier.height(8.dp))
			}

			items(serverUrls, key = { it }) { url ->
				var showEditDialog by remember { mutableStateOf(false) }

				if (showEditDialog) {
					EditHostDialog(
						currentUrl = url,
						onDismiss = { showEditDialog = false },
						onConfirm = { newUrl ->
							if (newUrl.isNotBlank() && newUrl != url) {
								onRemoveServerUrl(url)
								onAddServerUrl(newUrl)
							}
							showEditDialog = false
						}
					)
				}

				Column(
					modifier = Modifier
						.fillMaxWidth()
						.background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.2f))
						.clickable(
							onClickLabel = "edit info",
							onClick = { showEditDialog = true }
						)
						.semantics {
							contentDescription = "Host $url"
							customActions = listOf(
								CustomAccessibilityAction("Remove") {
									onRemoveServerUrl(url)
									true
								}
							)
						}
				) {
					Row(
						verticalAlignment = Alignment.CenterVertically,
						modifier = Modifier
							.padding(horizontal = 8.dp, vertical = 4.dp)
							.fillMaxWidth()
							.clearAndSetSemantics { }
					) {
						Text(
							text = url,
							modifier = Modifier
								.weight(1f)
								.padding(vertical = 12.dp)
						)
						IconButton(
							onClick = { onRemoveServerUrl(url) }
						) {
							Icon(Icons.Default.Delete, contentDescription = null)
						}
					}
					HorizontalDivider()
				}
			}

			item {
				var newHostUrl by remember { mutableStateOf("ws://") }
				val focusManager = LocalFocusManager.current
				OutlinedTextField(
					value = newHostUrl, onValueChange = { newHostUrl = it },
					label = { Text("Add new host URL") }, singleLine = true,
					keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
					keyboardActions = KeyboardActions(onDone = { onAddServerUrl(newHostUrl); newHostUrl="ws://"; focusManager.clearFocus() }),
					modifier = Modifier.fillMaxWidth().padding(top=4.dp),
					trailingIcon = { IconButton(onClick = { onAddServerUrl(newHostUrl); newHostUrl="ws://"; focusManager.clearFocus() }) { Icon(Icons.Default.Add, "Add Host") } }
				)
				Spacer(modifier = Modifier.height(16.dp))
			}

			item {
				OutlinedTextField(value = providerName, onValueChange = onProviderNameChange, label = { Text("Provider Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
				Spacer(modifier = Modifier.height(16.dp))
			}

			item {
				Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
					Button(onClick = onStartStopClick, modifier = Modifier.weight(1f)) { Text(if (isServiceRunning) "Stop Provider" else "Start Provider") }
					Spacer(Modifier.width(8.dp))
					IconButton(onClick = onConfigureEnginesClick) { Icon(Icons.Filled.Build, contentDescription = "Configure Engines") }
					IconButton(onClick = onConfigureVoicesClick) { Icon(Icons.Filled.Settings, contentDescription = "Configure Voices") }
				}
				Spacer(modifier = Modifier.height(16.dp))
			}

			item {
				Text(currentStatus, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.fillMaxWidth())
				Spacer(modifier = Modifier.height(16.dp))
				Text("Logs:", style = MaterialTheme.typography.titleSmall, modifier = Modifier.fillMaxWidth())
			}

			item {
				Box(modifier = Modifier.fillMaxWidth().height(200.dp).background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)).padding(8.dp)) { Text(text = logMessages, modifier = Modifier.fillMaxSize().verticalScroll(logScrollState), style = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 12.sp))
				}
			}
		}
	}
}

@Composable
fun EditHostDialog(currentUrl: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
	var editedUrl by remember { mutableStateOf(currentUrl) }
	AlertDialog(
		onDismissRequest = onDismiss,
		title = { Text("Edit Host URL") },
		text = {
			OutlinedTextField(
				value = editedUrl,
				onValueChange = { editedUrl = it },
				label = { Text("Host URL") },
				singleLine = true,
				modifier = Modifier.fillMaxWidth(),
				keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
				keyboardActions = KeyboardActions(onDone = { onConfirm(editedUrl) })
			)
		},
		confirmButton = { Button(onClick = { onConfirm(editedUrl) }) { Text("Save") } },
		dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
	)
}

@Composable
fun EngineConfigurationDialog(onDismiss: () -> Unit, starProviderService: StarProviderService?) {
	var engineConfigItems by remember { mutableStateOf<List<DialogEngineInfo>>(emptyList()) }
	var isLoading by remember { mutableStateOf(true) }

	LaunchedEffect(starProviderService) {
		isLoading = true
		if (starProviderService != null) {
			engineConfigItems = withContext(Dispatchers.IO) {
				starProviderService.getSystemEnginesForConfiguration()
			}
		}
		isLoading = false
	}

	Dialog(onDismissRequest = onDismiss) {
		Surface(modifier = Modifier.fillMaxWidth(0.95f).fillMaxHeight(0.85f), shape = MaterialTheme.shapes.medium, tonalElevation = AlertDialogDefaults.TonalElevation) {
			Column(modifier = Modifier.padding(16.dp)) {
				Text("Configure TTS Engines", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(bottom = 16.dp))
				
				if (isLoading) {
					Box(modifier = Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
				} else if (engineConfigItems.isEmpty()) {
					Box(modifier = Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
						Text("No TTS engines found or service not ready.", modifier = Modifier.padding(16.dp))
					}
				} else {
					val listState = rememberLazyListState()
					LazyColumn(
						modifier = Modifier
							.fillMaxWidth()
							.weight(1f)
							.semantics {
								collectionInfo = CollectionInfo(rowCount = engineConfigItems.size, columnCount = 1)
								verticalScrollAxisRange = ScrollAxisRange(
									value = { listState.firstVisibleItemIndex.toFloat() },
									maxValue = { engineConfigItems.size.toFloat() }
								)
								horizontalScrollAxisRange = ScrollAxisRange(value = { 0f }, maxValue = { 0f })
							},
						state = listState
					) {
						itemsIndexed(engineConfigItems) { index, engine ->
							EngineItem(
								engine = engine,
								onEnabledChange = { pkg, isEnabled ->
									engineConfigItems = engineConfigItems.map {
										if (it.packageName == pkg) it.copy(isEnabled = isEnabled) else it
									}
								},
								index = index
							)
						}
					}
				}

				Spacer(modifier = Modifier.height(16.dp))
				Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
					TextButton(onClick = onDismiss) { Text("Cancel") }
					Spacer(modifier = Modifier.width(8.dp))
					Button(onClick = {
						val configsToSave = engineConfigItems.associate { it.packageName to it.isEnabled }
						starProviderService?.saveAndReloadEngineConfigs(configsToSave)
						onDismiss()
					}, enabled = !isLoading && engineConfigItems.isNotEmpty()) { Text("Save & Apply") }
				}
			}
		}
	}
}

@Composable
fun EngineItem(engine: DialogEngineInfo, onEnabledChange: (String, Boolean) -> Unit, index: Int) {
	Column(
		modifier = Modifier
			.fillMaxWidth()
			.semantics {
				collectionItemInfo = CollectionItemInfo(rowIndex = index, rowSpan = 1, columnIndex = 0, columnSpan = 1)
			}
	) {
		Row(
			verticalAlignment = Alignment.CenterVertically,
			modifier = Modifier
				.padding(vertical = 8.dp, horizontal = 16.dp)
				.fillMaxWidth()
		) {
			Column(modifier = Modifier.weight(1f)) {
				Text(text = engine.label, fontSize = 18.sp, color = MaterialTheme.colorScheme.onSurface)
				Text(text = engine.packageName, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
			}
			Switch(
				checked = engine.isEnabled,
				onCheckedChange = { onEnabledChange(engine.packageName, it) },
				modifier = Modifier.padding(start = 8.dp)
			)
		}
		HorizontalDivider()
	}
}


data class VoiceConfigItem(
	val id: String,
	val displayName: String,
	var alias: String,
	var isEnabled: Boolean,
	val locale: String,
	val isNetwork: Boolean
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VoiceConfigurationDialog(
	onDismiss: () -> Unit,
	starProviderService: StarProviderService?
) {

	var voiceConfigItems by remember { mutableStateOf<List<VoiceConfigItem>>(emptyList()) }
	var isLoading by remember { mutableStateOf(true) }

	LaunchedEffect(starProviderService) {
		isLoading = true
		if (starProviderService != null) {
			val systemVoicesData = withContext(Dispatchers.IO) {
				starProviderService.getSystemVoicesForConfiguration()
			}
			voiceConfigItems = systemVoicesData.map { dialogInfo ->
				val engineShortName = dialogInfo.engineName.split('.').lastOrNull() ?: dialogInfo.engineName
				VoiceConfigItem(
					id = "${dialogInfo.engineName}:${dialogInfo.originalName}",
					displayName = "${dialogInfo.originalName} (${dialogInfo.locale.toLanguageTag()}, Engine: $engineShortName)",
					alias = dialogInfo.currentAlias,
					isEnabled = dialogInfo.currentIsEnabled,
					locale = dialogInfo.locale.toLanguageTag(),
					isNetwork = dialogInfo.isNetwork
				)
			}
		}
		isLoading = false
	}

	Dialog(onDismissRequest = onDismiss) {
		Surface(modifier = Modifier.fillMaxWidth(0.95f).fillMaxHeight(0.85f), shape = MaterialTheme.shapes.medium, tonalElevation = AlertDialogDefaults.TonalElevation) {
			Column(modifier = Modifier.padding(16.dp)) {
				Text("Configure Voices", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(bottom = 16.dp))
				
				if (isLoading) {
					Box(modifier = Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
				} else if (voiceConfigItems.isEmpty()) {
					Box(modifier = Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
						Text("No voices available. Check TTS engine configuration or logs.", modifier = Modifier.padding(16.dp))
					}
				} else {
					val listState = rememberLazyListState()
					LazyColumn(
						modifier = Modifier
							.fillMaxWidth()
							.weight(1f)
							.semantics {
								collectionInfo = CollectionInfo(rowCount = voiceConfigItems.size, columnCount = 1)
								verticalScrollAxisRange = ScrollAxisRange(
									value = { listState.firstVisibleItemIndex.toFloat() },
									maxValue = { voiceConfigItems.size.toFloat() }
								)
								horizontalScrollAxisRange = ScrollAxisRange(value = { 0f }, maxValue = { 0f })
							},
						state = listState
					) {
						itemsIndexed(
							items = voiceConfigItems,
							key = { _, item -> item.id }
						) { index, voiceItem ->
							VoiceItem(
								item = voiceItem,
								onAliasChange = { id, newAlias ->
									voiceConfigItems = voiceConfigItems.map { if (it.id == id) it.copy(alias = newAlias) else it }
								},
								onEnabledChange = { id, isEnabled ->
									voiceConfigItems = voiceConfigItems.map { if (it.id == id) it.copy(isEnabled = isEnabled) else it }
								},
								index = index
							)
						}
					}
				}

				Spacer(modifier = Modifier.height(16.dp))
				Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
					TextButton(onClick = onDismiss) { Text("Cancel") }
					Spacer(modifier = Modifier.width(8.dp))
					Button(
						onClick = {
							val configsToSave = voiceConfigItems.mapNotNull { item ->
									val idParts = item.id.split(":", limit = 2)
									if (idParts.size == 2) {
										PersistedVoiceConfig(originalName = idParts[1], engineName = idParts[0], starLabel = item.alias, isEnabled = item.isEnabled)
									} else {
										Log.w("MainActivity", "Skipping invalid voice config item with ID: ${item.id}")
										null
									}
								}
							starProviderService?.savePersistedVoiceConfigs(configsToSave)
							onDismiss()
						},
					enabled = !isLoading && voiceConfigItems.isNotEmpty()
					) { Text("Save & Apply") }
				}
			}
		}
	}
}

@Composable
fun VoiceItem(
	item: VoiceConfigItem,
	onAliasChange: (String, String) -> Unit,
	onEnabledChange: (String, Boolean) -> Unit,
	index: Int
) {
	Column(
		modifier = Modifier
			.fillMaxWidth()
			.semantics {
				collectionItemInfo = CollectionItemInfo(rowIndex = index, rowSpan = 1, columnIndex = 0, columnSpan = 1)
			}
	) {
		Row(
			verticalAlignment = Alignment.CenterVertically,
			modifier = Modifier
				.padding(vertical = 4.dp, horizontal = 16.dp)
				.fillMaxWidth()
		) {
			Column(modifier = Modifier.weight(1f)) {
				Text(text = item.displayName, fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurface)
				OutlinedTextField(
					value = item.alias,
					onValueChange = { onAliasChange(item.id, it) },
					label = { Text("Alias") },
					singleLine = true,
					textStyle = TextStyle(fontSize = 14.sp),
					modifier = Modifier
						.fillMaxWidth()
						.padding(top = 2.dp)
				)
			}
			Switch(
				checked = item.isEnabled,
				onCheckedChange = { onEnabledChange(item.id, it) },
				modifier = Modifier
					.padding(start = 8.dp)
					.semantics { contentDescription = "Enable voice ${item.alias.ifBlank { item.displayName }}" }
			)
		}
		HorizontalDivider()
	}
}

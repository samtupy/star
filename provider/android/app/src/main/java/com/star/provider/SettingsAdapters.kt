package com.star.provider

import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.appcompat.widget.SwitchCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.textfield.TextInputEditText
import com.star.provider.R

class EngineAdapter(
	private var engines: List<DialogEngineInfo>,
	private val onEnabledChange: (String, Boolean) -> Unit
) : RecyclerView.Adapter<EngineAdapter.ViewHolder>() {

	class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
		val label: TextView = view.findViewById(R.id.engine_label)
		val packageName: TextView = view.findViewById(R.id.engine_package)
		val switch: SwitchCompat = view.findViewById(R.id.engine_switch)
	}

	override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
		val view = LayoutInflater.from(parent.context).inflate(R.layout.item_engine, parent, false)
		return ViewHolder(view)
	}

	override fun onBindViewHolder(holder: ViewHolder, position: Int) {
		val engine = engines[position]
		holder.label.text = engine.label
		holder.packageName.text = engine.packageName
		
		holder.switch.setOnCheckedChangeListener(null)
		holder.switch.isChecked = engine.isEnabled
		holder.switch.setOnCheckedChangeListener { _, isChecked ->
			onEnabledChange(engine.packageName, isChecked)
		}
	}

	override fun getItemCount() = engines.size

	fun updateData(newEngines: List<DialogEngineInfo>) {
		val diffCallback = object : DiffUtil.Callback() {
			override fun getOldListSize() = engines.size
			override fun getNewListSize() = newEngines.size
			override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
				return engines[oldItemPosition].packageName == newEngines[newItemPosition].packageName
			}
			override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
				return engines[oldItemPosition] == newEngines[newItemPosition]
			}
		}
		val diffResult = DiffUtil.calculateDiff(diffCallback)
		engines = newEngines
		diffResult.dispatchUpdatesTo(this)
	}
}

class VoiceAdapter(
	private var voices: List<VoiceConfigItem>,
	private val onAliasChange: (String, String) -> Unit,
	private val onEnabledChange: (String, Boolean) -> Unit
) : RecyclerView.Adapter<VoiceAdapter.ViewHolder>() {

	class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
		val displayName: TextView = view.findViewById(R.id.voice_display_name)
		val aliasEdit: TextInputEditText = view.findViewById(R.id.voice_alias_edit)
		val switch: SwitchCompat = view.findViewById(R.id.voice_switch)
	}

	override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
		val view = LayoutInflater.from(parent.context).inflate(R.layout.item_voice, parent, false)
		return ViewHolder(view)
	}

	override fun onBindViewHolder(holder: ViewHolder, position: Int) {
		val voice = voices[position]
		holder.displayName.text = voice.displayName
		
		// Remove old listener if it exists
		(holder.aliasEdit.tag as? TextWatcher)?.let {
			holder.aliasEdit.removeTextChangedListener(it)
		}
		
		// Only update text if it's different to preserve cursor/composition
		if (holder.aliasEdit.text.toString() != voice.alias) {
			holder.aliasEdit.setText(voice.alias)
		}
		
		val textWatcher = object : TextWatcher {
			override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
			override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
			override fun afterTextChanged(s: Editable?) {
				val pos = holder.bindingAdapterPosition
				if (pos != RecyclerView.NO_POSITION) {
					val newText = s?.toString() ?: ""
					if (newText != voices[pos].alias) {
						onAliasChange(voices[pos].id, newText)
					}
				}
			}
		}
		holder.aliasEdit.tag = textWatcher
		holder.aliasEdit.addTextChangedListener(textWatcher)

		holder.switch.setOnCheckedChangeListener(null)
		holder.switch.isChecked = voice.isEnabled
		holder.switch.contentDescription = "Enable voice ${voice.alias.ifBlank { voice.displayName }}"
		holder.switch.setOnCheckedChangeListener { _, isChecked ->
			val pos = holder.bindingAdapterPosition
			if (pos != RecyclerView.NO_POSITION) {
				onEnabledChange(voices[pos].id, isChecked)
			}
		}
	}

	override fun onViewRecycled(holder: ViewHolder) {
		super.onViewRecycled(holder)
		val textWatcher = holder.aliasEdit.tag as? TextWatcher
		if (textWatcher != null) {
			holder.aliasEdit.removeTextChangedListener(textWatcher)
		}
	}

	override fun getItemCount() = voices.size

	fun updateData(newVoices: List<VoiceConfigItem>) {
		val diffCallback = object : DiffUtil.Callback() {
			override fun getOldListSize() = voices.size
			override fun getNewListSize() = newVoices.size
			override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
				return voices[oldItemPosition].id == newVoices[newItemPosition].id
			}
			override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int): Boolean {
				return voices[oldItemPosition] == newVoices[newItemPosition]
			}
		}
		val diffResult = DiffUtil.calculateDiff(diffCallback)
		voices = newVoices
		diffResult.dispatchUpdatesTo(this)
	}
}
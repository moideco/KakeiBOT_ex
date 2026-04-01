package com.kakeichi.app

import android.os.Bundle
import android.view.inputmethod.EditorInfo
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.chip.Chip
import com.kakeichi.app.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private val currentCategories = mutableListOf<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        supportActionBar?.title = getString(R.string.settings)

        loadSettings()

        binding.addCategoryButton.setOnClickListener { addCategory() }
        binding.newCategoryInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) { addCategory(); true } else false
        }
        binding.saveButton.setOnClickListener { saveSettings() }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun loadSettings() {
        val prefs = getSharedPreferences(MainActivity.PREFS_NAME, MODE_PRIVATE)
        binding.webhookUrlInput.setText(prefs.getString(MainActivity.KEY_WEBHOOK_URL, ""))

        val saved = prefs.getString(MainActivity.KEY_CATEGORIES, MainActivity.DEFAULT_CATEGORIES)
        currentCategories.clear()
        saved?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.forEach { addCategoryChip(it) }
    }

    private fun addCategory() {
        val name = binding.newCategoryInput.text?.toString()?.trim() ?: ""
        when {
            name.isEmpty() -> showToast("カテゴリ名を入力してください")
            currentCategories.contains(name) -> showToast("「$name」はすでに登録されています")
            else -> {
                addCategoryChip(name)
                binding.newCategoryInput.text?.clear()
            }
        }
    }

    private fun addCategoryChip(name: String) {
        currentCategories.add(name)
        val chip = Chip(this).apply {
            text = name
            isCloseIconVisible = true
            isClickable = false
            setOnCloseIconClickListener {
                binding.categoriesChipGroup.removeView(this)
                currentCategories.remove(name)
            }
        }
        binding.categoriesChipGroup.addView(chip)
    }

    private fun saveSettings() {
        val webhookUrl = binding.webhookUrlInput.text?.toString()?.trim() ?: ""
        if (webhookUrl.isNotEmpty() && !webhookUrl.startsWith("https://discord.com/api/webhooks/")) {
            showToast("Webhook URL の形式が正しくありません")
            return
        }

        getSharedPreferences(MainActivity.PREFS_NAME, MODE_PRIVATE).edit().apply {
            putString(MainActivity.KEY_WEBHOOK_URL, webhookUrl)
            putString(MainActivity.KEY_CATEGORIES, currentCategories.joinToString(","))
            apply()
        }

        showToast("設定を保存しました")
        finish()
    }

    private fun showToast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }
}

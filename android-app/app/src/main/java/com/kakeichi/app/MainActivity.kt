package com.kakeichi.app

import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.chip.Chip
import com.kakeichi.app.databinding.ActivityMainBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val client = OkHttpClient()
    private var selectedCategory: String? = null
    private var selectedCurrency: String = "JPY"
    private var displayString: String = "0"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        setupNumpad()
        setupCurrencyToggle()
        loadCategories()
    }

    override fun onResume() {
        super.onResume()
        loadCategories()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                startActivity(Intent(this, SettingsActivity::class.java))
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun loadCategories() {
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val categoriesStr = prefs.getString(KEY_CATEGORIES, DEFAULT_CATEGORIES)
        val categories = categoriesStr
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?: DEFAULT_CATEGORIES.split(",").map { it.trim() }

        binding.categoryGrid.removeAllViews()
        selectedCategory = null
        updateCategoryDisplay()

        val bgColors = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
            intArrayOf(
                ContextCompat.getColor(this, R.color.calc_chip_selected),
                ContextCompat.getColor(this, R.color.calc_chip_bg)
            )
        )

        categories.forEach { category ->
            val chip = Chip(this).apply {
                text = category
                isCheckable = true
                chipBackgroundColor = bgColors
                setTextColor(Color.WHITE)
                chipStrokeWidth = 0f
                chipCornerRadius = 8f
            }
            binding.categoryGrid.addView(chip)
        }

        binding.categoryGrid.setOnCheckedStateChangeListener { group, checkedIds ->
            selectedCategory = if (checkedIds.isEmpty()) {
                null
            } else {
                group.findViewById<Chip>(checkedIds[0])?.text?.toString()
            }
            updateCategoryDisplay()
        }
    }

    private fun updateCategoryDisplay() {
        binding.categoryDisplay.text = selectedCategory ?: "カテゴリなし"
    }

    private fun setupCurrencyToggle() {
        binding.currencyToggleGroup.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (isChecked) {
                selectedCurrency = when (checkedId) {
                    R.id.btnJpy -> "JPY"
                    R.id.btnUsd -> "USD"
                    else -> "JPY"
                }
            }
        }
    }

    private fun setupNumpad() {
        binding.btn0.setOnClickListener { appendDigit("0") }
        binding.btn1.setOnClickListener { appendDigit("1") }
        binding.btn2.setOnClickListener { appendDigit("2") }
        binding.btn3.setOnClickListener { appendDigit("3") }
        binding.btn4.setOnClickListener { appendDigit("4") }
        binding.btn5.setOnClickListener { appendDigit("5") }
        binding.btn6.setOnClickListener { appendDigit("6") }
        binding.btn7.setOnClickListener { appendDigit("7") }
        binding.btn8.setOnClickListener { appendDigit("8") }
        binding.btn9.setOnClickListener { appendDigit("9") }
        binding.btnDecimal.setOnClickListener { appendDecimal() }
        binding.btnClear.setOnClickListener { clearDisplay() }
        binding.btnBackspace.setOnClickListener { backspace() }
        binding.btnSign.setOnClickListener { toggleSign() }
        binding.btnSend.setOnClickListener { send() }
    }

    private fun appendDigit(digit: String) {
        val isNeg = displayString.startsWith("-")
        val abs = displayString.removePrefix("-")
        if (abs == "0") {
            displayString = if (isNeg) "-$digit" else digit
        } else {
            // 小数部を含めて10桁まで
            if (abs.replace(".", "").length >= 10) return
            displayString += digit
        }
        updateDisplay()
    }

    private fun appendDecimal() {
        if ("." in displayString) return
        displayString = if (displayString == "0") "0." else "$displayString."
        updateDisplay()
    }

    private fun backspace() {
        displayString = when {
            displayString.length <= 1 -> "0"
            else -> {
                val result = displayString.dropLast(1)
                if (result == "-" || result.isEmpty()) "0" else result
            }
        }
        updateDisplay()
    }

    private fun clearDisplay() {
        displayString = "0"
        updateDisplay()
    }

    private fun toggleSign() {
        displayString = if (displayString.startsWith("-")) {
            displayString.drop(1)
        } else {
            if (displayString == "0") "0" else "-$displayString"
        }
        updateDisplay()
    }

    private fun updateDisplay() {
        binding.amountDisplay.text = displayString
    }

    private fun send() {
        val amount = displayString.toDoubleOrNull()
        if (amount == null || amount == 0.0) {
            showToast("金額を入力してください")
            return
        }

        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val webhookUrl = prefs.getString(KEY_WEBHOOK_URL, "")
        if (webhookUrl.isNullOrEmpty()) {
            showToast("設定から Discord Webhook URL を登録してください")
            startActivity(Intent(this, SettingsActivity::class.java))
            return
        }

        // カテゴリなしの場合は "<金額> <通貨>" → Bot側で食費扱い
        val message = buildString {
            append(displayString)
            if (selectedCategory != null) append(" $selectedCategory")
            append(" $selectedCurrency")
        }

        sendToDiscord(webhookUrl, message)
    }

    private fun sendToDiscord(webhookUrl: String, message: String) {
        binding.btnSend.isEnabled = false

        CoroutineScope(Dispatchers.IO).launch {
            val success = try {
                val json = JSONObject().apply { put("content", message) }
                val body = json.toString()
                    .toRequestBody("application/json; charset=utf-8".toMediaType())
                val request = Request.Builder().url(webhookUrl).post(body).build()
                client.newCall(request).execute().use { it.isSuccessful }
            } catch (e: Exception) {
                false
            }

            withContext(Dispatchers.Main) {
                binding.btnSend.isEnabled = true
                if (success) {
                    showToast("✅ 送信しました")
                    clearDisplay()
                    binding.categoryGrid.clearCheck()
                    selectedCategory = null
                    updateCategoryDisplay()
                } else {
                    showToast("❌ 送信に失敗しました")
                }
            }
        }
    }

    private fun showToast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    companion object {
        const val PREFS_NAME = "kakei_prefs"
        const val KEY_WEBHOOK_URL = "webhook_url"
        const val KEY_CATEGORIES = "categories"
        const val DEFAULT_CATEGORIES = "食費,家賃,娯楽"
    }
}

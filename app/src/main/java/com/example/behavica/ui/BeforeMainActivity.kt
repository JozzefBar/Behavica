package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Patterns
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.behavica.R
import com.example.behavica.data.UserEmailHandler
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

class BeforeMainActivity : AppCompatActivity() {

    private lateinit var emailLayout: TextInputLayout
    private lateinit var emailInput: TextInputEditText
    private lateinit var startButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var emailStatusText: TextView

    private val handler = UserEmailHandler()
    private var resolvedUserId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.before_main_activity)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.beforeMain)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        emailLayout = findViewById(R.id.emailLayout)
        emailInput = findViewById(R.id.emailInput)
        startButton = findViewById(R.id.startButton)
        progressBar = findViewById(R.id.emailCheckProgress)
        emailStatusText = findViewById(R.id.emailStatusText)

        startButton.isEnabled = false

        handler.ensureAnonAuth(
            onReady = {},
            onError = { showStatus(it) }
        )

        emailInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun afterTextChanged(s: Editable?) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val email = s?.toString()?.trim().orEmpty()
                val isValid = Patterns.EMAIL_ADDRESS.matcher(email).matches()

                if (startButton.text.toString().contains("Error")) {
                    startButton.text = "Start"
                }

                emailLayout.error = when {
                    email.isEmpty() -> "Email is required"
                    !isValid -> "Invalid email format"
                    else -> null
                }
                emailLayout.helperText = if (isValid) "Looks good" else null

                emailStatusText.visibility = View.GONE
                emailStatusText.text = ""
                resolvedUserId = null

                if (isValid) {
                    handler.debounceEmailCheck(
                        email = email,
                        onStart = {
                            progressBar.visibility = View.VISIBLE
                            startButton.isEnabled = false
                            startButton.text = "Checking..."
                        },
                        onResult = { uid, msg, exists ->
                            progressBar.visibility = View.GONE
                            showStatus(msg)
                            resolvedUserId = uid
                            startButton.isEnabled = true
                            startButton.text = "Start"
                        },
                        onError = {
                            progressBar.visibility = View.GONE
                            showStatus("Error: $it\nPlease check your connection and try again")
                            emailStatusText.setTextColor(resources.getColor(android.R.color.holo_red_dark, null))
                            startButton.isEnabled = false
                            startButton.text = "Connection Error"
                        }
                    )
                }
            }
        })

        startButton.setOnClickListener {
            val email = emailInput.text.toString().trim()
            progressBar.visibility = View.VISIBLE
            startButton.isEnabled = false

            if (resolvedUserId == null) {
                handler.generateNewUserId(
                    onSuccess = { newUserId ->
                        progressBar.visibility = View.GONE
                        goToMain(email, newUserId)
                    },
                    onError = {
                        progressBar.visibility = View.GONE
                        showStatus(it)
                        startButton.isEnabled = true
                    }
                )
            } else {
                progressBar.visibility = View.GONE
                goToMain(email, resolvedUserId)
            }
        }
    }

    private fun showStatus(message: String) {
        emailStatusText.visibility = View.VISIBLE
        emailStatusText.text = message
    }

    private fun goToMain(email: String, userId: String?) {
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("email", email)
            if (!userId.isNullOrBlank()) putExtra("userId", userId)
        }
        startActivity(intent)
        finish()
    }
}
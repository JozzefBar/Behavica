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
import com.example.behavica.data.FirestoreRepository
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import android.os.Handler
import android.os.Looper
import com.example.behavica.data.AppStartHandler

class EmailCheckActivity : AppCompatActivity() {

    private lateinit var emailLayout: TextInputLayout
    private lateinit var emailInput: TextInputEditText
    private lateinit var startButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView

    private val repo by lazy { FirestoreRepository(FirebaseFirestore.getInstance(), this) }
    private val auth by lazy { FirebaseAuth.getInstance() }
    private val appStartHandler by lazy { AppStartHandler(this) }

    private val handler = Handler(Looper.getMainLooper())
    private var pendingCheck: Runnable? = null
    private var emailChecked = false
    private var emailAvailable = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        checkAppStart()
    }

    override fun onDestroy() {
        super.onDestroy()
        // Cleanup handler to prevent memory leak
        pendingCheck?.let { handler.removeCallbacks(it) }
    }

    private fun checkAppStart() {
        appStartHandler.determineStartDestination(
            onResult = { destination ->
                when (destination) {
                    is AppStartHandler.StartDestination.EmailCheck -> {
                        initializeEmailCheckScreen()
                    }
                    is AppStartHandler.StartDestination.Ending -> {
                        goToFinalScreen()
                    }
                }
            },
            onError = { error ->
                // On error, show email check screen
                initializeEmailCheckScreen()
            }
        )
    }

    private fun initializeEmailCheckScreen() {
        enableEdgeToEdge()
        setContentView(R.layout.email_check_activity)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.emailCheck)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        initViews()
        ensureAnonAuth()
        setupEmailWatcher()
        setupStartButton()
    }

    private fun initViews() {
        emailLayout = findViewById(R.id.emailLayout)
        emailInput = findViewById(R.id.emailInput)
        startButton = findViewById(R.id.startButton)
        progressBar = findViewById(R.id.checkProgress)
        statusText = findViewById(R.id.statusText)
        startButton.isEnabled = false
    }

    private fun ensureAnonAuth() {
        if (auth.currentUser != null) return

        auth.signInAnonymously()
            .addOnFailureListener { e ->
                showStatus(getString(R.string.auth_failed, e.message), true)
            }
    }

    private fun setupEmailWatcher() {
        emailInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun afterTextChanged(s: Editable?) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val email = s?.toString()?.trim().orEmpty()
                val isValid = Patterns.EMAIL_ADDRESS.matcher(email).matches()

                // Update input field error state
                emailInput.error = when {
                    email.isEmpty() -> getString(R.string.email_required)
                    !isValid -> getString(R.string.invalid_email_format)
                    else -> null
                }
                emailLayout.helperText = if (isValid) getString(R.string.checking) else null

                // Reset status
                statusText.visibility = View.GONE
                emailChecked = false
                emailAvailable = false
                startButton.isEnabled = false

                // Cancel any pending check
                pendingCheck?.let { handler.removeCallbacks(it) }

                // Debounce email check (only if valid format)
                if (isValid) {
                    pendingCheck = Runnable {
                        checkEmailInDatabase(email)
                    }
                    handler.postDelayed(pendingCheck!!, 500) // 500ms delay
                }
            }
        })
    }

    private fun checkEmailInDatabase(email: String) {
        progressBar.visibility = View.VISIBLE
        startButton.isEnabled = false
        statusText.visibility = View.GONE

        repo.checkEmailExists(
            email = email.trim().lowercase(),
            onResult = { exists, message ->
                progressBar.visibility = View.GONE
                emailChecked = true
                emailAvailable = !exists

                if (exists) {
                    emailLayout.helperText = null
                    showStatus(message, true)
                    startButton.isEnabled = false
                } else {
                    emailLayout.helperText = getString(R.string.email_available)
                    showStatus(message, false)
                    startButton.isEnabled = true
                }
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                emailLayout.helperText = null
                showStatus(getString(R.string.error_checking_email, error), true)
                startButton.isEnabled = false
                emailChecked = false
                emailAvailable = false
            }
        )
    }

    private fun setupStartButton() {
        startButton.setOnClickListener {
            val email = emailInput.text.toString().trim().lowercase()

            // Cancel any pending debounced check
            pendingCheck?.let { handler.removeCallbacks(it) }

            // Validate email format
            if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
                showStatus(getString(R.string.please_enter_valid_email), true)
                return@setOnClickListener
            }

            // If email was already checked and is available, proceed directly
            if (emailChecked && emailAvailable) {
                generateUserIdAndProceed(email)
                return@setOnClickListener
            }

            // Otherwise, check email one more time before proceeding
            progressBar.visibility = View.VISIBLE
            startButton.isEnabled = false
            startButton.text = getString(R.string.checking)

            repo.checkEmailExists(
                email = email,
                onResult = { exists, message ->
                    if (exists) {
                        progressBar.visibility = View.GONE
                        showStatus(message, true)
                        startButton.isEnabled = true
                        startButton.text = getString(R.string.start)
                    } else {
                        generateUserIdAndProceed(email)
                    }
                },
                onError = { error ->
                    progressBar.visibility = View.GONE
                    showStatus(getString(R.string.error_generic, error), true)
                    startButton.isEnabled = true
                    startButton.text = getString(R.string.start)
                }
            )
        }
    }

    private fun generateUserIdAndProceed(email: String) {
        startButton.text = getString(R.string.generating_id)
        startButton.isEnabled = false
        progressBar.visibility = View.VISIBLE

        repo.generateUniqueUserIdOnly(
            onResult = { userId ->
                progressBar.visibility = View.GONE
                goToMetadata(userId, email)
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                showStatus(getString(R.string.error_generic, error), true)
                startButton.isEnabled = true
                startButton.text = getString(R.string.start)
            }
        )
    }

    private fun showStatus(message: String, isError: Boolean = false) {
        statusText.visibility = View.VISIBLE
        statusText.text = message
        statusText.setTextColor(
            if (isError) resources.getColor(android.R.color.holo_red_dark, null)
            else resources.getColor(android.R.color.holo_green_dark, null)
        )
    }

    private fun goToMetadata(userId: String, email: String) {
        val intent = Intent(this, MetadataActivity::class.java).apply {
            putExtra("userId", userId)
            putExtra("email", email)
        }
        startActivity(intent)
        finish()
    }

    private fun goToFinalScreen() {
        startActivity(Intent(this, EndingActivity::class.java))
        finish()
    }
}
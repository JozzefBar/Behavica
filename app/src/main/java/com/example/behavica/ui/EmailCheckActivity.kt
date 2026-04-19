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
import androidx.core.view.isVisible
import com.example.behavica.data.AppStartHandler

class EmailCheckActivity : AppCompatActivity() {

    private lateinit var startText: TextView
    private lateinit var emailLayout: TextInputLayout
    private lateinit var emailInput: TextInputEditText
    private lateinit var startDataLoggingButton: Button
    private lateinit var authenticateButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var infoText: TextView

    private val repo by lazy { FirestoreRepository(FirebaseFirestore.getInstance(), this) }
    private val auth by lazy { FirebaseAuth.getInstance() }
    private val appStartHandler by lazy { AppStartHandler(this) }

    private val handler = Handler(Looper.getMainLooper())
    private var pendingCheck: Runnable? = null
    private var blockedUserId: String? = null
    private var blockedEmail: String? = null
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
                    is AppStartHandler.StartDestination.EmailCheckBlocked -> {
                        initializeEmailCheckScreen()
                        blockedUserId = destination.userId
                        blockedEmail = destination.email
                        showDeviceBlockedError(destination.message)
                    }
                }
            },
            onError = { error ->
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
        setupButtons()
    }

    private fun initViews() {
        startText = findViewById(R.id.startText)
        emailLayout = findViewById(R.id.emailLayout)
        emailInput = findViewById(R.id.emailInput)
        startDataLoggingButton = findViewById(R.id.startDataLoggingButton)
        authenticateButton = findViewById(R.id.authenticateButton)
        progressBar = findViewById(R.id.checkProgress)
        statusText = findViewById(R.id.statusText)
        infoText = findViewById(R.id.infoText)
        startDataLoggingButton.isEnabled = false
        authenticateButton.isEnabled = false
    }

    private fun showDeviceBlockedError(message: String) {
        startText.isVisible = false
        emailLayout.isVisible = false
        emailInput.isEnabled = false
        startDataLoggingButton.isEnabled = false
        startDataLoggingButton.isVisible = false
        authenticateButton.isEnabled = true
        infoText.isVisible = false
        showStatus(message, false)
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
                startDataLoggingButton.isEnabled = false
                authenticateButton.isEnabled = false

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
        startDataLoggingButton.isEnabled = false
        authenticateButton.isEnabled = false
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
                    startDataLoggingButton.isEnabled = false
                    authenticateButton.isEnabled = true
                } else {
                    // During the data logging phase, new users could register here.
                    // Now that the logging phase is closed, only users who already
                    // logged data can authenticate — new emails are rejected.
                    // Old behavior:
                    // emailLayout.helperText = null
                    // showStatus(message, false)
                    // startDataLoggingButton.isEnabled = true
                    // authenticateButton.isEnabled = false
                    emailLayout.helperText = null
                    showStatus(getString(R.string.logging_phase_closed), true)
                    startDataLoggingButton.isEnabled = false
                    authenticateButton.isEnabled = false
                }
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                emailLayout.helperText = null
                showStatus(getString(R.string.error_checking_email, error), true)
                startDataLoggingButton.isEnabled = false
                authenticateButton.isEnabled = false
                emailChecked = false
                emailAvailable = false
            }
        )
    }

    private fun setupButtons() {
        // Data Logging button is disabled — the logging phase is over.
        // Only users who already logged data can now authenticate.
        // The button remains in the layout but is permanently disabled.
        startDataLoggingButton.isEnabled = false

        // Old behavior during the data logging phase:
        // startDataLoggingButton.setOnClickListener {
        //     val email = emailInput.text.toString().trim().lowercase()
        //     pendingCheck?.let { handler.removeCallbacks(it) }
        //     if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
        //         showStatus(getString(R.string.please_enter_valid_email), true)
        //         return@setOnClickListener
        //     }
        //     if (emailChecked && emailAvailable) {
        //         generateUserIdAndProceed(email)
        //         return@setOnClickListener
        //     }
        //     progressBar.visibility = View.VISIBLE
        //     startDataLoggingButton.isEnabled = false
        //     startDataLoggingButton.text = getString(R.string.checking)
        //     repo.checkEmailExists(
        //         email = email,
        //         onResult = { exists, message ->
        //             if (exists) {
        //                 progressBar.visibility = View.GONE
        //                 showStatus(message, true)
        //                 startDataLoggingButton.isEnabled = true
        //                 startDataLoggingButton.text = getString(R.string.start_data_logging)
        //             } else {
        //                 generateUserIdAndProceed(email)
        //             }
        //         },
        //         onError = { error ->
        //             progressBar.visibility = View.GONE
        //             showStatus(getString(R.string.error_generic, error), true)
        //             startDataLoggingButton.isEnabled = true
        //             startDataLoggingButton.text = getString(R.string.start_data_logging)
        //         }
        //     )
        // }

        // Authentication Button
        authenticateButton.setOnClickListener {
            goToAuthenticationSubmission()
        }
    }

    private fun generateUserIdAndProceed(email: String) {
        startDataLoggingButton.text = getString(R.string.generating_id)
        startDataLoggingButton.isEnabled = false
        progressBar.visibility = View.VISIBLE

        repo.generateUniqueUserIdOnly(
            onResult = { userId ->
                progressBar.visibility = View.GONE
                goToMetadata(userId, email)
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                showStatus(getString(R.string.error_generic, error), true)
                startDataLoggingButton.isEnabled = true
                startDataLoggingButton.text = getString(R.string.start_data_logging)
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

    private fun goToAuthenticationSubmission() {
        // If device was blocked, use stored userId/email from DB
        if (blockedUserId != null) {
            val intent = Intent(this, SubmissionActivity::class.java).apply {
                putExtra("userId", blockedUserId)
                putExtra("userEmail", blockedEmail ?: "")
                putExtra("submissionNumber", 1)
                putExtra("isAuthentication", true)
            }
            startActivity(intent)
            finish()
            return
        }

        // Otherwise, look up userId by email from input field
        val email = emailInput.text.toString().trim().lowercase()
        progressBar.visibility = View.VISIBLE
        authenticateButton.isEnabled = false

        repo.fetchUserIdByEmail(
            email = email,
            onResult = { userId ->
                val intent = Intent(this, SubmissionActivity::class.java).apply {
                    putExtra("userId", userId)
                    putExtra("userEmail", email)
                    putExtra("submissionNumber", 1)
                    putExtra("isAuthentication", true)
                }
                startActivity(intent)
                finish()
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                authenticateButton.isEnabled = true
                showStatus(getString(R.string.error_generic, error), true)
            }
        )
    }
}
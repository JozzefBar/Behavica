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

    private val repo by lazy { FirestoreRepository(FirebaseFirestore.getInstance()) }
    private val auth by lazy { FirebaseAuth.getInstance() }
    private val appStartHandler by lazy { AppStartHandler() }

    private val handler = Handler(Looper.getMainLooper())
    private var pendingCheck: Runnable? = null
    private var emailChecked = false
    private var emailExists = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.email_check_activity)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.emailCheck)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        checkAppStart()
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
                showStatus("Auth failed: ${e.message}", true)
            }
    }

    private fun setupEmailWatcher() {
        emailInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun afterTextChanged(s: Editable?) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val email = s?.toString()?.trim().orEmpty()
                val isValid = Patterns.EMAIL_ADDRESS.matcher(email).matches()

                emailInput.error = when {
                    email.isEmpty() -> "Email is required"
                    !isValid -> "Invalid email format"
                    else -> null
                }
                emailLayout.helperText = if (isValid) "Looks good" else null

                statusText.visibility = View.GONE
                emailChecked = false
                emailExists = false
                startButton.isEnabled = false

                // Debounce email check
                if (isValid) {
                    pendingCheck?.let { handler.removeCallbacks(it) }
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
            email = email.lowercase(),
            onResult = { exists, message ->
                progressBar.visibility = View.GONE
                emailChecked = true
                emailExists = exists

                if (exists) {
                    showStatus(message, true)
                    startButton.isEnabled = false
                } else {
                    showStatus(message, false)
                    startButton.isEnabled = true
                }
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                showStatus("Error checking email: $error", true)
                startButton.isEnabled = false
            }
        )
    }

    private fun setupStartButton() {
        startButton.setOnClickListener {
            val email = emailInput.text.toString().trim().lowercase()

            progressBar.visibility = View.VISIBLE
            startButton.isEnabled = false
            startButton.text = "Checking..."

            repo.checkEmailExists(
                email = email,
                onResult = { exists, message ->
                    if (exists) {
                        progressBar.visibility = View.GONE
                        showStatus(message, true)
                        startButton.isEnabled = true
                        startButton.text = "Start"
                    } else {
                        generateUserIdAndProceed(email)
                    }
                },
                onError = { error ->
                    progressBar.visibility = View.GONE
                    showStatus("Error: $error", true)
                    startButton.isEnabled = true
                    startButton.text = "Start"
                }
            )
        }
    }

    private fun generateUserIdAndProceed(email: String) {
        startButton.text = "Generating ID..."

        repo.generateUniqueUserIdOnly(
            onResult = { userId ->
                progressBar.visibility = View.GONE
                showStatus("User ID generated: $userId", false)
                goToMetadata(userId, email)
            },
            onError = { error ->
                progressBar.visibility = View.GONE
                showStatus("Error: $error", true)
                startButton.isEnabled = true
                startButton.text = "Start"
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
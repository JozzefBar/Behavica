package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.example.behavica.data.FirestoreRepository
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreException
import com.google.firebase.firestore.Source

class BeforeMainActivity : AppCompatActivity() {
    private lateinit var emailLayout: TextInputLayout
    private lateinit var emailInput: TextInputEditText
    private lateinit var startButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var emailStatusText: TextView

    private val db by lazy { FirebaseFirestore.getInstance() }
    private val repo by lazy { FirestoreRepository(db) }
    private val auth by lazy { FirebaseAuth.getInstance() }

    //for userID from db
    private var resolvedUserId: String? = null

    // Debounce + safety check before new response from server
    private val handler = Handler(Looper.getMainLooper())
    private var pendingCheck: Runnable? = null
    private var queryToken = 0
    private var lastFinishedToken = -1
    private var authReady = false

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

        ensureAnonAuth { authReady = true }

        emailInput.addTextChangedListener(object : TextWatcher{
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int){}
            override fun onTextChanged(s: CharSequence?, start: Int, count: Int, after: Int){
                val email = s?.toString()?.trim().orEmpty()
                val isValid = Patterns.EMAIL_ADDRESS.matcher(email).matches()

                startButton.isEnabled = isValid
                emailLayout.error = when {
                    email.isEmpty() -> "Email is required"
                    !isValid -> "Invalid email format"
                    else -> null
                }
                emailLayout.helperText = if (isValid) "Looks good" else null

                emailStatusText.visibility = View.GONE
                emailStatusText.text = ""
                resolvedUserId = null

                // Debounce 300 ms
                pendingCheck?.let { handler.removeCallbacks(it) }
                if (!isValid) return

                val token = ++queryToken
                pendingCheck = Runnable {
                    // wait for auth
                    if (!authReady) {
                        ensureAnonAuth {
                            authReady = true
                            doServerCheck(email.lowercase(), token)
                        }
                    } else {
                        doServerCheck(email.lowercase(), token)
                    }
                }
                handler.postDelayed(pendingCheck!!, 300)
            }

            override fun afterTextChanged(p0: Editable?) {}
        })

        startButton.setOnClickListener {
                val email = emailInput.text.toString().trim()
                startButton.isEnabled = false
                progressBar.visibility = View.VISIBLE

                ensureAnonAuth {
                    if (resolvedUserId == null) {
                        repo.generateUniqueUserIdOnly(
                            onResult = { newUserId ->
                                progressBar.visibility = View.GONE
                                resolvedUserId = newUserId
                                goToMain(email, newUserId)
                            },
                            onError = { msg ->
                                progressBar.visibility = View.GONE
                                startButton.isEnabled = true
                                emailStatusText.visibility = View.VISIBLE
                                emailStatusText.text = msg
                            }
                        )
                    } else {
                        progressBar.visibility = View.GONE
                        goToMain(email, resolvedUserId)
                    }
                }
        }
    }

    // anonymous login
    private fun ensureAnonAuth(onReady: () -> Unit) {
        if (auth.currentUser != null) {
            onReady()
            return
        }
        progressBar.visibility = View.VISIBLE
        auth.signInAnonymously()
            .addOnSuccessListener {
                progressBar.visibility = View.GONE
                onReady()
            }
            .addOnFailureListener { e ->
                progressBar.visibility = View.GONE
                val msg = (e as? FirebaseAuthException)?.errorCode ?: e.localizedMessage
                emailStatusText.visibility = View.VISIBLE
                emailStatusText.text = "Auth failed: $msg"
            }
    }

    private fun doServerCheck(emailLower: String, token: Int) {
        progressBar.visibility = View.VISIBLE
        startButton.isEnabled = false

        db.collection("Users2").document(emailLower)
            .get(Source.SERVER)
            .addOnSuccessListener { snap ->
                if (token <= lastFinishedToken) return@addOnSuccessListener
                lastFinishedToken = token
                progressBar.visibility = View.GONE
                emailStatusText.visibility = View.VISIBLE

                if (snap.exists()) {
                    val count = (snap.getLong("submissionCount") ?: 0).toInt()
                    val uid = snap.getString("userId")
                    resolvedUserId = uid

                    val countMsg = "This email already has $count submission(s)."
                    val idMsg = if (!uid.isNullOrBlank())
                        "User ID: $uid"
                    else
                        "No user ID stored for this email"

                    emailStatusText.text = "$countMsg  $idMsg"
                    emailLayout.helperText = "Email OK"
                    emailLayout.error = null
                    startButton.isEnabled = true
                }
                else {
                    resolvedUserId = null
                    emailStatusText.text = "This email is not in the database yet. User ID will be generated after clicking Start."
                    emailLayout.helperText = "Email OK"
                    emailLayout.error = null
                    startButton.isEnabled = true
                }
            }
            .addOnFailureListener { e ->
                if (token <= lastFinishedToken) return@addOnFailureListener
                lastFinishedToken = token
                progressBar.visibility = View.GONE
                val code = (e as? FirebaseFirestoreException)?.code?.name ?: e.localizedMessage
                emailStatusText.text = "Couldn't check DB: $code"
                emailStatusText.visibility = View.VISIBLE
                emailLayout.error = null
            }
    }

    private fun goToMain(email: String, userId: String?) {
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("email", email)
            if (!userId.isNullOrBlank())
                putExtra("userId", userId)
        }
        startActivity(intent)
        finish()
    }
}
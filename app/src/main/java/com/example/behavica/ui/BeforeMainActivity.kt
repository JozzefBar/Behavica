package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.util.Log
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
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthException
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreException

class BeforeMainActivity : AppCompatActivity() {
    private lateinit var emailLayout: TextInputLayout
    private lateinit var emailInput: TextInputEditText
    private lateinit var startButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var emailStatusText: TextView

    private val db by lazy { FirebaseFirestore.getInstance() }
    private val auth by lazy { FirebaseAuth.getInstance() }

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

                if (isValid) {
                    val emailLower = email.trim().lowercase()
                    ensureAnonAuth {
                        checkEmailInDb(emailLower)
                    }
                }
            }
            override fun afterTextChanged(p0: Editable?) {}
        })

        startButton.setOnClickListener {
            val email = emailInput.text.toString().trim()
            goToMain(email)
        }
    }

    // anonymous login in
    private fun ensureAnonAuth(onReady: () -> Unit) {
        if (auth.currentUser != null) { onReady(); return }
        progressBar.visibility = View.VISIBLE
        auth.signInAnonymously()
            .addOnSuccessListener {
                progressBar.visibility = View.GONE
                onReady()
            }
            .addOnFailureListener { e ->
                progressBar.visibility = View.GONE
                val msg = (e as? FirebaseAuthException)?.errorCode ?: e.localizedMessage
                emailStatusText.text = "Auth failed: $msg"
                emailStatusText.visibility = View.VISIBLE
                Log.e("Auth", "Anon sign-in failed", e)
            }
    }

    private fun checkEmailInDb(emailLower: String) {
        progressBar.visibility = View.VISIBLE

        db.collection("Users2").document(emailLower)
            .get()
            .addOnSuccessListener { snap ->
                progressBar.visibility = View.GONE

                emailStatusText.visibility = View.VISIBLE
                val count = (snap.getLong("submissionCount") ?: -1).toInt()
                if (count > 0)
                    emailStatusText.text = "This email already has $count submission(s)."
                else
                    emailStatusText.text = "This email is not in the database yet."

                emailLayout.helperText = "Email OK"
                emailLayout.error = null
            }
            .addOnFailureListener { e ->
                progressBar.visibility = View.GONE
                val code = (e as? FirebaseFirestoreException)?.code?.name ?: e.localizedMessage
                emailStatusText.text = "Couldn't check DB: $code"
                emailStatusText.visibility = View.VISIBLE
                Log.e("DB", "read failed", e)
                emailLayout.error = null
            }
    }

    private fun goToMain(email: String) {
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("email", email)
        }
        startActivity(intent)
        finish()
    }
}
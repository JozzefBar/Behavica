package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.widget.*
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.behavica.R
import com.example.behavica.data.FirestoreRepository
import com.example.behavica.sensors.HandDetector
import com.example.behavica.validation.MetadataValidator
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class MetadataActivity : AppCompatActivity() {

    private lateinit var userIdText: TextView
    private lateinit var emailText: TextView
    private lateinit var userAgeLayout: TextInputLayout
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkbox: CheckBox
    private lateinit var saveButton: Button

    // Firebase
    private lateinit var db: FirebaseFirestore
    private val auth by lazy { FirebaseAuth.getInstance() }

    // Email from pre-screen
    private var userEmail: String? = null
    private var userId: String? = null

    // Helpers
    private lateinit var hand: HandDetector
    private lateinit var repo: FirestoreRepository
    private lateinit var validator: MetadataValidator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.metadata_activity)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.metadata)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        db = FirebaseFirestore.getInstance()

        userId = intent.getStringExtra("userId")
        userEmail = intent.getStringExtra("email")

        initViews()
        displayUserInfo()

        // helpers init
        hand = HandDetector(this).also { it.start() }
        repo = FirestoreRepository(db)
        validator = MetadataValidator(userAgeLayout, genderSpinner, checkbox)

        // Setups
        setupGenderSpinner()
        setupSaveButton()

        // Ignore Back button
        val callback = object : OnBackPressedCallback(true) { override fun handleOnBackPressed() {} }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    private fun initViews() {
        userIdText = findViewById(R.id.userIdText)
        emailText = findViewById(R.id.emailText)
        userAgeLayout = findViewById(R.id.userAgeLayout)
        userAgeInput = findViewById(R.id.userAgeInput)
        genderSpinner = findViewById(R.id.genderSpinner)
        checkbox = findViewById(R.id.checkBox)
        saveButton = findViewById(R.id.saveButton)
    }

    private fun displayUserInfo() {
        userIdText.text = "User ID: ${userId ?: "—"}"
        emailText.text = "Email: ${userEmail ?: "—"}"
    }

    private fun setupGenderSpinner() {
        val genderOptions = arrayOf("Select Gender", "Male", "Female", "Other")
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genderOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        genderSpinner.adapter = adapter
    }

    private fun setupSaveButton() {
        saveButton.setOnClickListener {
            val validationResult = validator.validateMetadata(userAgeInput.text.toString().trim())

            if (validationResult.isValid) {
                saveButton.isEnabled = false
                saveButton.text = "Saving..."
                ensureAnonAuthThen { saveMetadata() }
            } else {
                Toast.makeText(this, validationResult.errorMessage, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun ensureAnonAuthThen(onReady: () -> Unit) {
        val user = auth.currentUser
        if (user != null) {
            onReady()
            return
        }
        auth.signInAnonymously()
            .addOnSuccessListener { onReady() }
            .addOnFailureListener { e ->
                Toast.makeText(this, "Auth failed: ${e.message}", Toast.LENGTH_LONG).show()
                saveButton.isEnabled = true
                saveButton.text = "Save & Continue"
            }
    }

    // Save to Firestore
    private fun saveMetadata() {
        val userIdStr = userId.orEmpty()
        val email = userEmail.orEmpty().trim().lowercase()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()

        repo.createUserMetadata(
            userId = userIdStr,
            email = email,
            userAge = userAge,
            userGender = userGender,
            onSuccess = {
                Toast.makeText(this, "Metadata saved successfully!", Toast.LENGTH_SHORT).show()
                goToSubmission(userIdStr)
            },
            onError = { eMsg ->
                Toast.makeText(this, eMsg, Toast.LENGTH_LONG).show()
                saveButton.isEnabled = true
                saveButton.text = "Save & Continue"
            }
        )
    }

    private fun goToSubmission(userId: String) {
        val intent = Intent(this, SubmissionActivity::class.java).apply {
            putExtra("userId", userId)
            putExtra("submissionNumber", 1)
        }
        startActivity(intent)
        finish()
    }
}
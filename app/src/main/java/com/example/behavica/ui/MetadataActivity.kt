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
import com.example.behavica.validation.MetadataValidator
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.firebase.firestore.FirebaseFirestore

class MetadataActivity : AppCompatActivity() {

    private lateinit var userIdText: TextView
    private lateinit var emailText: TextView
    private lateinit var userAgeLayout: TextInputLayout
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var dominantHandSpinner: Spinner
    private lateinit var checkbox: CheckBox
    private lateinit var saveButton: Button

    // Firebase
    private lateinit var db: FirebaseFirestore

    // Email from pre-screen
    private var userEmail: String? = null
    private var userId: String? = null

    // Helpers
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
        repo = FirestoreRepository(db, this)
        validator = MetadataValidator(userAgeLayout, genderSpinner, dominantHandSpinner, checkbox)

        // Setups
        setupGenderSpinner()
        setupDominantHandSpinner()
        setupSaveButton()

        // Ignore Back button
        val callback = object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                Toast.makeText(this@MetadataActivity, R.string.please_complete_form, Toast.LENGTH_SHORT).show()
            }
        }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    private fun initViews() {
        userIdText = findViewById(R.id.userIdText)
        emailText = findViewById(R.id.emailText)
        userAgeLayout = findViewById(R.id.userAgeLayout)
        userAgeInput = findViewById(R.id.userAgeInput)
        genderSpinner = findViewById(R.id.genderSpinner)
        dominantHandSpinner = findViewById(R.id.dominantHandSpinner)
        checkbox = findViewById(R.id.checkBox)
        saveButton = findViewById(R.id.saveButton)
    }

    private fun displayUserInfo() {
        userIdText.text = getString(R.string.user_id_label, userId ?: "—")
        emailText.text = getString(R.string.email_label, userEmail ?: "—")
    }

    private fun setupGenderSpinner() {
        val genderOptions = arrayOf(
            getString(R.string.select_gender),
            getString(R.string.male),
            getString(R.string.female),
            getString(R.string.other)
        )
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genderOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        genderSpinner.adapter = adapter
    }

    private fun setupDominantHandSpinner() {
        val handOptions = arrayOf(
            getString(R.string.select_dominant_hand),
            getString(R.string.right_handed),
            getString(R.string.left_handed),
            getString(R.string.ambidextrous)
        )
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, handOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        dominantHandSpinner.adapter = adapter
    }

    private fun setupSaveButton() {
        saveButton.setOnClickListener {
            val validationResult = validator.validateMetadata(userAgeInput.text.toString().trim())

            if (validationResult.isValid) {
                saveButton.isEnabled = false
                saveButton.text = getString(R.string.saving)
                repo.ensureAnonAuth(
                    onReady = { saveMetadata() },
                    onError = { error ->
                        Toast.makeText(this, error, Toast.LENGTH_LONG).show()
                        saveButton.isEnabled = true
                        saveButton.text = getString(R.string.save_continue)
                    }
                )
            } else {
                Toast.makeText(this, validationResult.errorMessage, Toast.LENGTH_LONG).show()
            }
        }
    }

    // Save to Firestore
    private fun saveMetadata() {
        val userIdStr = userId.orEmpty()
        val email = userEmail.orEmpty().trim().lowercase()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()
        val dominantHand = dominantHandSpinner.selectedItem.toString()

        repo.createUserMetadata(
            userId = userIdStr,
            email = email,
            userAge = userAge,
            userGender = userGender,
            dominantHand = dominantHand,
            onSuccess = {
                Toast.makeText(this, R.string.metadata_saved, Toast.LENGTH_SHORT).show()
                goToSubmission(userIdStr)
            },
            onError = { eMsg ->
                Toast.makeText(this, eMsg, Toast.LENGTH_LONG).show()
                saveButton.isEnabled = true
                saveButton.text = getString(R.string.save_continue)
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
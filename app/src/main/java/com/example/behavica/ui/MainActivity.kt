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
import com.example.behavica.logging.BehaviorTracker
import com.example.behavica.metrics.FormMetrics
import com.example.behavica.sensors.HandDetector
import com.example.behavica.validation.FormValidator
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore

class MainActivity : AppCompatActivity() {

    private lateinit var userIdLayout: TextInputLayout
    private lateinit var userIdInput: TextInputEditText
    private lateinit var userAgeLayout: TextInputLayout
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkBox: CheckBox
    private lateinit var submitButton: Button

    // Firebase
    private lateinit var db: FirebaseFirestore
    private val auth by lazy { FirebaseAuth.getInstance() }

    // Email from pre-screen
    private var userEmail: String? = null

    // Helpers
    private lateinit var metrics: FormMetrics
    private lateinit var behavior: BehaviorTracker
    private lateinit var hand: HandDetector
    private lateinit var repo: FirestoreRepository
    private lateinit var validator: FormValidator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.afterSubmit)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        db = FirebaseFirestore.getInstance()
        userEmail = intent.getStringExtra("email")

        initViews()

        // helpers init
        metrics = FormMetrics().apply { markFormStart() }
        behavior = BehaviorTracker(metrics)
        behavior.attach(userIdInput, userAgeInput, genderSpinner, checkBox, submitButton)

        hand = HandDetector(this).also { it.start() }
        repo = FirestoreRepository(db)
        validator = FormValidator(userIdLayout, userAgeLayout, genderSpinner, checkBox)

        setupGenderSpinner()
        setupSubmitButton()

        // Ignore Back button
        val callback = object : OnBackPressedCallback(true) { override fun handleOnBackPressed() {} }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    override fun onDestroy() {
        super.onDestroy()
        hand.stop()
    }

    private fun initViews() {
        userIdLayout = findViewById(R.id.userIdLayout)
        userAgeLayout = findViewById(R.id.userAgeLayout)
        userIdInput = findViewById(R.id.userIdInput)
        userAgeInput = findViewById(R.id.userAgeInput)
        genderSpinner = findViewById(R.id.genderSpinner)
        checkBox = findViewById(R.id.checkBox)
        submitButton = findViewById(R.id.submitButton)
    }

    private fun setupGenderSpinner() {
        val genderOptions = arrayOf("Select Gender", "Male", "Female", "Other")
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genderOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        genderSpinner.adapter = adapter
    }

    private fun setupSubmitButton() {
        submitButton.setOnClickListener {
            metrics.markSubmitClick()

            if (validator.validateForm()) {
                submitButton.isEnabled = false
                submitButton.text = "Submitting..."
                ensureAnonAuthThen { submitToFirebase() }
            }
        }
    }

    private fun ensureAnonAuthThen(onReady: () -> Unit) {
        val user = auth.currentUser
        if (user != null) { onReady(); return }
        auth.signInAnonymously()
            .addOnSuccessListener { onReady() }
            .addOnFailureListener { e ->
                android.util.Log.e("Auth", "Anon sign-in failed", e)
                Toast.makeText(this, "Permission denied (auth).", Toast.LENGTH_LONG).show()
                submitButton.isEnabled = true
                submitButton.text = "Submit"
            }
    }

    // Save to Firestore
    private fun submitToFirebase() {
        val userId = userIdInput.text.toString().trim()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()

        repo.submit(
            email = userEmail.toString().trim(),
            userId = userId,
            userAge = userAge,
            userGender = userGender,
            handHeld = hand.currentHand(),
            metrics = metrics,
            touchPoints = behavior.getTouchPoints(),
            onSuccess = {
                Toast.makeText(this, "Data saved successfully!", Toast.LENGTH_SHORT).show()
                startActivity(Intent(this, AfterSubmitActivity::class.java))
                finish()
            },
            onError = { eMsg ->
                Toast.makeText(this, eMsg, Toast.LENGTH_LONG).show()
                submitButton.isEnabled = true
                submitButton.text = "Submit"
            }
        )
    }
}
package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.annotation.SuppressLint
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

    private lateinit var userIdText: TextView
    private lateinit var userAgeLayout: TextInputLayout
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkBox: CheckBox
    private lateinit var submitButton: Button

    private lateinit var startCircle: View
    private lateinit var endCircle: View
    private lateinit var draggableCircle: View
    private lateinit var dragContainer: FrameLayout
    private lateinit var dragStatusText: TextView

    // Firebase
    private lateinit var db: FirebaseFirestore
    private val auth by lazy { FirebaseAuth.getInstance() }

    // Email from pre-screen
    private var userEmail: String? = null
    private var userId: String? = null

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
        userId = intent.getStringExtra("userId")

        initViews()
        userIdText.text = "UserID: ${userId ?: "—"}"

        // helpers init
        metrics = FormMetrics().apply { markFormStart() }
        behavior = BehaviorTracker(metrics)
        behavior.attach(userAgeInput, genderSpinner, checkBox, submitButton)

        metrics.onDragStatusChanged = { completed ->
            runOnUiThread { updateDragStatus() }
        }

        hand = HandDetector(this).also { it.start() }
        repo = FirestoreRepository(db)
        validator = FormValidator(userAgeLayout, genderSpinner, checkBox, metrics)

        // Setups
        setupGenderSpinner()
        setupSubmitButton()
        setupDragTest()

        // Ignore Back button
        val callback = object : OnBackPressedCallback(true) { override fun handleOnBackPressed() {} }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    override fun onDestroy() {
        super.onDestroy()
        hand.stop()
    }

    private fun initViews() {
        userIdText = findViewById(R.id.userIdText)
        userAgeLayout = findViewById(R.id.userAgeLayout)
        userAgeInput = findViewById(R.id.userAgeInput)
        genderSpinner = findViewById(R.id.genderSpinner)
        checkBox = findViewById(R.id.checkBox)
        submitButton = findViewById(R.id.submitButton)
        startCircle = findViewById(R.id.startPoint)
        endCircle = findViewById(R.id.endPoint)
        draggableCircle = findViewById(R.id.draggableCircle)
        dragContainer = findViewById(R.id.moveTestContainer)
        dragStatusText = findViewById(R.id.dragStatusText)
    }

    private fun setupGenderSpinner() {
        val genderOptions = arrayOf("Select Gender", "Male", "Female", "Other")
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, genderOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        genderSpinner.adapter = adapter
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupDragTest() {
        behavior.attachDragTracking(
            draggable = draggableCircle,
            start = startCircle,
            end = endCircle,
            container = dragContainer
        )

        // Monitor metrics to show visual feedback
        draggableCircle.post {
            draggableCircle.setOnLongClickListener {
                // Long click detection - optional for additional analytics
                false
            }
        }
    }

    // Call this to update drag status after each attempt
    private fun updateDragStatus() {
        if (metrics.dragCompleted) {
            dragStatusText.text = "✓ Drag test completed!"
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_green_dark, null))
            dragStatusText.visibility = View.VISIBLE
        } else if (metrics.dragAttempts > 0) {
            dragStatusText.text = "Please try again - drag the circle all the way to B"
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_red_dark, null))
            dragStatusText.visibility = View.VISIBLE
        }
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
        val email = userEmail.orEmpty().trim().lowercase()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()

        repo.submitWithMetrics(
            email = email,
            userAge = userAge,
            userGender = userGender,
            handHeld = hand.currentHand(),
            metrics = metrics,
            touchPoints = behavior.getTouchPoints(),
            existingUserId = userId,
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
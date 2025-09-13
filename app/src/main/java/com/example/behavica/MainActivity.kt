package com.example.behavica

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.view.MotionEvent
import android.widget.*
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.constraintlayout.widget.ConstraintLayout
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.firebase.firestore.FirebaseFirestore
import java.text.SimpleDateFormat
import java.util.*

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

    // Behavior data
    private val userIdTimestamps = mutableListOf<Long>()
    private var userIdBackspaces = 0
    private var userIdStartTime: Long = 0

    private val userAgeTimestamps = mutableListOf<Long>()
    private var userAgeBackspaces = 0
    private var userAgeStartTime: Long = 0

    private val clickPositions = mutableListOf<Pair<Float, Float>>()

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
        initViews()
        setupGenderSpinner()
        setupSubmitButton()
        setupBehaviorTracking()
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
            if(validateForm()){
                submitButton.isEnabled = false
                submitButton.text = "Submitting..."

                submitToFirebase()
            }
        }
    }

    private fun validateForm(): Boolean {
        val userId = userIdInput.text.toString().trim()
        if(userId.isEmpty()) {
            userIdLayout.error = "Please enter a valid user id"
            return false
        }

        if(userId.count() != 5) {
            userIdLayout.error = "Please user id must contain 5 characters"
            return false
        }
        userIdLayout.error = null

        val userAgeStr = userAgeInput.text.toString().trim()
        if(userAgeStr.isEmpty()){
            userAgeLayout.error = "Please enter a valid user age"
            return false
        }

        val userAge = userAgeStr.toInt()
        if(userAge < 10 || userAge > 100){
            userAgeLayout.error = "Please age must be between 10 and 100"
            return false
        }
        userAgeLayout.error = null

        if(genderSpinner.selectedItemPosition == 0){
            Toast.makeText(this, "Please select your gender", Toast.LENGTH_LONG).show()
            return false
        }

        if(!checkBox.isChecked){
            Toast.makeText(this, "You must agree to biometric data collection", Toast.LENGTH_LONG).show()
            return false
        }

        return true
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupBehaviorTracking() {
        // Track userId input
        userIdInput.setOnKeyListener { _, keyCode, event ->
            if (event.action == android.view.KeyEvent.ACTION_DOWN) {
                if (userIdStartTime == 0L) userIdStartTime = System.currentTimeMillis()
                if (keyCode == android.view.KeyEvent.KEYCODE_DEL) userIdBackspaces++
                userIdTimestamps.add(System.currentTimeMillis())
            }
            false
        }

        // Track userAge input
        userAgeInput.setOnKeyListener { _, keyCode, event ->
            if (event.action == android.view.KeyEvent.ACTION_DOWN) {
                if (userAgeStartTime == 0L) userAgeStartTime = System.currentTimeMillis()
                if (keyCode == android.view.KeyEvent.KEYCODE_DEL) userAgeBackspaces++
                userAgeTimestamps.add(System.currentTimeMillis())
            }
            false
        }

        // Track clicks anywhere
        findViewById<ConstraintLayout>(R.id.afterSubmit).setOnTouchListener { _, event ->
            if (event.action == MotionEvent.ACTION_DOWN) {
                clickPositions.add(Pair(event.x, event.y))
            }
            false
        }
    }

    private fun submitToFirebase() {
        val userId = userIdInput.text.toString().trim()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()

        // creation of timestamp
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        val currentTime = dateFormat.format(Date())

        val userIdTypingTime = if (userIdStartTime != 0L) System.currentTimeMillis() - userIdStartTime else -1
        val userAgeTypingTime = if (userAgeStartTime != 0L) System.currentTimeMillis() - userAgeStartTime else -1

        // create behavioral data structure for Firebase
        val behaviorData = hashMapOf(
            "userIdTypingTime" to userIdTypingTime,
            "userIdBackspaces" to userIdBackspaces,
            "userIdKeystrokes" to userIdTimestamps,
            "userAgeTypingTime" to userAgeTypingTime,
            "userAgeBackspaces" to userAgeBackspaces,
            "userAgeKeystrokes" to userAgeTimestamps,
            "clickPositions" to clickPositions
        )

        // create user data structure for Firebase
        val userData = hashMapOf(
            "userId" to userId,
            "age" to userAge,
            "gender" to userGender,
            "timestamp" to currentTime,
            "deviceModel" to android.os.Build.MODEL,
            "androidVersion" to android.os.Build.VERSION.RELEASE,
            "behavior" to behaviorData
        )

        // Save to Firestore
        db.collection("users")
            .add(userData)
            .addOnSuccessListener { documentReference ->
                // Saved successfully
                Toast.makeText(this, "Data saved successfully!", Toast.LENGTH_SHORT).show()

                // Go to AfterSubmitActivity
                val intent = Intent(this, AfterSubmitActivity::class.java)
                startActivity(intent)
                finish()
            }
            .addOnFailureListener { e ->
                // Error handling
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true ->
                        "Permission denied. Please check your data."
                    e.message?.contains("NETWORK") == true ->
                        "Network error. Please check your internet connection."
                    else ->
                        "Error saving data: ${e.message}"
                }

                Toast.makeText(this, errorMessage, Toast.LENGTH_LONG).show()

                // Re-enable button
                submitButton.isEnabled = true
                submitButton.text = "Submit"

                // Log error for debugging
                android.util.Log.e("Firebase", "Error adding document", e)
            }
    }
}
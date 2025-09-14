package com.example.behavica

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.*
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
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

    // TouchPoint data class
    private val touchPoints = mutableListOf<TouchPoint>()
    data class TouchPoint(val x: Float, val y: Float, val timestampTime: String, val target: String)

    // Behavioral data
    private var userIdStartTime: Long = 0
    private var userIdEndTime: Long = 0
    private var userIdEditCount = 0
    private var userIdMaxLength = 0

    private var userAgeStartTime: Long = 0
    private var userAgeEndTime: Long = 0
    private var userAgeEditCount = 0

    private var genderSelectTime: Long = 0
    private var checkboxClickTime: Long = 0
    private var submitClickTime: Long = 0
    private var formStartTime: Long = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.afterSubmit)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }
        formStartTime = System.currentTimeMillis()
        db = FirebaseFirestore.getInstance()

        initViews()
        setupGenderSpinner()
        setupSubmitButton()
        setupBehaviorTracking()

        // Ignore Back button
        val callback = object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
            }
        }
        onBackPressedDispatcher.addCallback(this, callback)
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
            val currentSubmitTime = System.currentTimeMillis()
            submitClickTime = currentSubmitTime

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

        //function for touch recording
        fun addTouchListener(view: android.view.View, targetName: String) {
            view.setOnTouchListener { _, event ->
                if (event.action == android.view.MotionEvent.ACTION_DOWN) {
                    val ts = System.currentTimeMillis()
                    val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
                    dateFormat.timeZone = TimeZone.getDefault()

                    touchPoints.add(
                        TouchPoint(
                            x = event.rawX,
                            y = event.rawY,
                            timestampTime = dateFormat.format(Date(ts)),
                            target = targetName
                        )
                    )
                }
                false
            }
        }

        // Track userId input
        userIdInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (userIdStartTime == 0L) userIdStartTime = System.currentTimeMillis()
                userIdEditCount++
                userIdMaxLength = maxOf(userIdMaxLength, s?.length ?: 0)
            }

            override fun afterTextChanged(s: Editable?) {
                userIdEndTime = System.currentTimeMillis()
            }
        })

        // Track userAge input
        userAgeInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (userAgeStartTime == 0L) userAgeStartTime = System.currentTimeMillis()
                userAgeEditCount++
            }

            override fun afterTextChanged(s: Editable?) {
                userAgeEndTime = System.currentTimeMillis()
            }
        })

        // Track gender spinner clicks
        genderSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                if (position > 0 && genderSelectTime == 0L) {
                    genderSelectTime = System.currentTimeMillis()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        // Track checkbox clicks
        checkBox.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && checkboxClickTime == 0L) {
                checkboxClickTime = System.currentTimeMillis()
            }
        }

        addTouchListener(userIdInput, "userIdInput")
        addTouchListener(userAgeInput, "userAgeInput")
        addTouchListener(genderSpinner, "genderSpinner")
        addTouchListener(checkBox, "checkBox")
        addTouchListener(submitButton, "submitButton")
    }

    private fun submitToFirebase() {
        val userId = userIdInput.text.toString().trim()
        val userAge = userAgeInput.text.toString().trim().toInt()
        val userGender = genderSpinner.selectedItem.toString()

        // creation of timestamp
        val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        dateFormat.timeZone = TimeZone.getDefault()
        val currentTime = dateFormat.format(Date())

        // Calculate behavioral metrics
        val totalFormTime = System.currentTimeMillis() - formStartTime
        val userIdTypingTime = if (userIdEndTime > userIdStartTime) userIdEndTime - userIdStartTime else -1
        val userAgeTypingTime = if (userAgeEndTime > userAgeStartTime) userAgeEndTime - userAgeStartTime else -1

        // Improved behavioral data
        val behaviorData = hashMapOf(
            "totalFormTime" to (totalFormTime / 1000.0),
            "userIdTypingTime" to (if (userIdTypingTime > 0) userIdTypingTime / 1000.0 else -1.0),
            "userIdEditCount" to userIdEditCount,
            "userIdMaxLength" to userIdMaxLength,
            "userAgeTypingTime" to (if (userAgeTypingTime > 0) userAgeTypingTime / 1000.0 else -1.0),
            "userAgeEditCount" to userAgeEditCount,
            "timeToSelectGender" to (if (genderSelectTime > 0) (genderSelectTime - formStartTime) / 1000.0 else -1.0),
            "timeToCheckbox" to (if (checkboxClickTime > 0) (checkboxClickTime - formStartTime) / 1000.0 else -1.0),
            "timeToSubmit" to (if (submitClickTime > 0) (submitClickTime - formStartTime) / 1000.0 else -1.0),
            "averageTypingSpeed" to (if (userIdTypingTime > 0) (userId.length.toDouble() / (userIdTypingTime / 1000.0)) else -1.0),
            "touchPointsCount" to touchPoints.size,
            "touchPoints" to touchPoints.map { mapOf(
                "x" to it.x,
                "y" to it.y,
                "timestamp" to it.timestampTime,
                "target" to it.target
            )}
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
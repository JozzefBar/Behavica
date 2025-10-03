package com.example.behavica

import android.annotation.SuppressLint
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
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
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import java.text.SimpleDateFormat
import java.util.*
import kotlin.math.abs
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.SetOptions

class MainActivity : AppCompatActivity(), SensorEventListener  {

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

    // TouchPoint data class
    private val touchPoints = mutableListOf<TouchPoint>()
    data class TouchPoint(val pressure: Float, val x: Float, val y: Float, val timestampTime: String, val target: String)

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

    // Hand detection
    private var handHeld: String = "unknown"
    private val handBuffer = mutableListOf<Triple<Float, Float, Float>>()
    private lateinit var gravity: FloatArray
    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null

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

        userEmail = intent.getStringExtra("email")

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

        // Sensor setup for hand detection
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_UI)

        handHeld = "unknown" //default
    }

    // SensorEventListener
    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return
        if (event.sensor.type == Sensor.TYPE_ACCELEROMETER) {

            val alpha = 0.8f
            if (!::gravity.isInitialized) gravity = FloatArray(3) { 0f }
            for (i in 0..2) {
                gravity[i] = alpha * gravity[i] + (1 - alpha) * event.values[i]
            }

            val x = gravity[0]
            val y = gravity[1]
            val z = gravity[2]

            handBuffer.add(Triple(x, y, z))
            if (handBuffer.size > 20) handBuffer.removeAt(0)

            val avgX = handBuffer.map { it.first }.average().toFloat()
            val avgY = handBuffer.map { it.second }.average().toFloat()
            val avgZ = handBuffer.map { it.third }.average().toFloat()

            val newHand = detectHand(avgX, avgY, avgZ)
            if (newHand != handHeld) {
                handHeld = newHand
                Toast.makeText(this, "Detected hand: $handHeld", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun detectHand(x: Float, y: Float, z: Float): String {
        val movementThreshold = 2.5f
        val horizontalThreshold = 1.5f

        if (abs(x) < horizontalThreshold && abs(y) < horizontalThreshold && abs(z - 9.8f) < horizontalThreshold) return "unknown"

        if (handHeld != "unknown") {
            return when {
                x > movementThreshold -> "left"
                x < -movementThreshold -> "right"
                else -> handHeld
            }
        }

        return when {
            x > movementThreshold -> "left"
            x < -movementThreshold -> "right"
            else -> handHeld
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        sensorManager.unregisterListener(this)
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
                    val pressure = event.pressure
                    val ts = System.currentTimeMillis()
                    val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
                    dateFormat.timeZone = TimeZone.getDefault()

                    touchPoints.add(
                        TouchPoint(
                            pressure = pressure,
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

        //safety ID for sub-collection
        val timestampId = currentTime.replace(" ", "_").replace(":", "-")

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
                "pressure" to it.pressure,
                "x" to it.x,
                "y" to it.y,
                "timestamp" to it.timestampTime,
                "target" to it.target
            )}
        )

        // create user data structure for Firebase
        val submission = hashMapOf(
            "userId" to userId,
            "age" to userAge,
            "gender" to userGender,
            "timestamp" to currentTime,
            "createdAt" to FieldValue.serverTimestamp(),
            "deviceModel" to android.os.Build.MODEL,
            "androidVersion" to android.os.Build.VERSION.RELEASE,
            "handUsed" to handHeld,
            "behavior" to behaviorData
        )

        val emailLower = (userEmail ?: "").trim().lowercase()
        val emailDoc = db.collection("Users2").document(emailLower)
        val subDoc = emailDoc.collection(timestampId).document("submission")

        //parent meta: submissionCount + lastSubmissionAt
        val parentMeta = mapOf(
            "email" to emailLower,
            "submissionCount" to FieldValue.increment(1),
            "lastSubmissionAt" to FieldValue.serverTimestamp()
        )

        // Save to Firestore
        val batch = db.batch()
        batch.set(emailDoc, parentMeta, SetOptions.merge())
        batch.set(subDoc, submission)

        batch.commit()
            .addOnSuccessListener {
                Toast.makeText(this, "Data saved successfully!", Toast.LENGTH_SHORT).show()
                startActivity(Intent(this, AfterSubmitActivity::class.java))
                finish()
            }
            .addOnFailureListener { e ->
                val errorMessage = when {
                    e.message?.contains("PERMISSION_DENIED") == true ->
                        "Permission denied. Please check your data."
                    e.message?.contains("NETWORK") == true ->
                        "Network error. Please check your internet connection."
                    else -> "Error saving data: ${e.message}"
                }
                Toast.makeText(this, errorMessage, Toast.LENGTH_LONG).show()
                submitButton.isEnabled = true
                submitButton.text = "Submit"
                android.util.Log.e("Firebase", "Error writing Users2/{email}/{timestamp}/submission", e)
            }
    }
}
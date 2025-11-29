package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.ActionMode
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import com.example.behavica.R
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.behavica.data.FirestoreRepository
import com.example.behavica.logging.BehaviorTracker
import com.example.behavica.sensors.SensorDataCollector
import com.example.behavica.validation.SubmissionValidator
import com.google.android.material.textfield.TextInputEditText
import com.google.firebase.firestore.FirebaseFirestore

class SubmissionActivity : AppCompatActivity() {

    private lateinit var submissionTitle: TextView
    private lateinit var startCircle: View
    private lateinit var endCircle: View
    private lateinit var draggableCircle: View
    private lateinit var dragContainer: FrameLayout
    private lateinit var dragStatusText: TextView

    private lateinit var targetTextView: TextView
    private lateinit var rewriteTextInput: TextInputEditText
    private lateinit var checkbox: CheckBox
    private lateinit var submitButton: Button

    private lateinit var db: FirebaseFirestore

    private var userId: String? = null
    private var submissionNumber: Int = 1

    private lateinit var behavior: BehaviorTracker
    private lateinit var sensorCollector: SensorDataCollector
    private lateinit var repo: FirestoreRepository
    private lateinit var validator: SubmissionValidator

    private val targetWords = listOf("internet", "wifi", "laptop")
    private var currentWordIndex = 0
    private var isProgrammaticChange = false    // change when word is correctly rewrote

    private var isAuthenticationMode = false
    private var userEmail: String? = null

    private val disableActionModeCallback = object : ActionMode.Callback {
        override fun onCreateActionMode(mode: ActionMode?, menu: Menu?): Boolean = false
        override fun onPrepareActionMode(mode: ActionMode?, menu: Menu?): Boolean = false
        override fun onActionItemClicked(mode: ActionMode?, item: MenuItem?): Boolean = false
        override fun onDestroyActionMode(mode: ActionMode?) {}
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.submission_activity)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.submission)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        db = FirebaseFirestore.getInstance()
        userId = intent.getStringExtra("userId")
        submissionNumber = intent.getIntExtra("submissionNumber", 1)

        userEmail = intent.getStringExtra("userEmail")
        isAuthenticationMode = intent.getBooleanExtra("isAuthentication", false)

        initViews()

        if (isAuthenticationMode) {
            submissionTitle.text = getString(R.string.authentication_title)
        } else {
            submissionTitle.text = getString(R.string.submission_title, submissionNumber)
        }

        targetTextView.text = getString(R.string.rewrite_text, targetWords[currentWordIndex])

        behavior = BehaviorTracker()
        behavior.submissionStartTime = System.currentTimeMillis()

        sensorCollector = SensorDataCollector(this).also { it.start() }
        repo = FirestoreRepository(db, this)
        validator = SubmissionValidator()

        behavior.onDragStatusChanged = { completed ->
            runOnUiThread { updateDragStatus() }
        }

        setupDragTest()
        setupTextInput()
        setupCheckbox()
        setupSubmitButton()

        behavior.attachTouchListener(rewriteTextInput, "rewriteTextInput")
        behavior.attachTouchListener(checkbox, "checkBox")
        behavior.attachTouchListener(submitButton, "submitButton")

        val callback = object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                Toast.makeText(this@SubmissionActivity, R.string.please_complete_submission, Toast.LENGTH_SHORT).show()
            }
        }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    override fun onDestroy(){
        super.onDestroy()
        sensorCollector.stop()
    }

    private fun initViews(){
        submissionTitle = findViewById(R.id.submissionTitle)
        startCircle = findViewById(R.id.startPoint)
        endCircle = findViewById(R.id.endPoint)
        draggableCircle = findViewById(R.id.draggableCircle)
        dragContainer = findViewById(R.id.moveTestContainer)
        dragStatusText = findViewById(R.id.dragStatusText)
        targetTextView = findViewById(R.id.targetTextView)
        rewriteTextInput = findViewById(R.id.rewriteTextInput)
        checkbox = findViewById(R.id.checkBox)
        submitButton = findViewById(R.id.submitButton)
    }

    private fun setupDragTest() {
        behavior.attachDragTracking(
            draggable = draggableCircle,
            start = startCircle,
            end = endCircle,
            container = dragContainer
        )
    }

    private fun setupTextInput(){
        behavior.attachTextWatcher(
            rewriteTextInput,
            getCurrentWord = {
                if (currentWordIndex < targetWords.size) {
                    targetWords[currentWordIndex]
                } else {
                    "completed"
                }
            },
            isProgrammaticChange = { isProgrammaticChange }
        )
        rewriteTextInput.addTextChangedListener(object: TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val input = s.toString().trim()

                if (currentWordIndex >= targetWords.size) {
                    return
                }

                if(input.equals(targetWords[currentWordIndex], ignoreCase = true)){
                    behavior.onWordCompleted()
                    currentWordIndex++

                    if(currentWordIndex < targetWords.size){
                        behavior.resetForNextWord()

                        isProgrammaticChange = true
                        rewriteTextInput.setText("")
                        isProgrammaticChange = false

                        targetTextView.text = getString(R.string.rewrite_text, targetWords[currentWordIndex])
                    }
                    else {
                        behavior.resetForNextWord()

                        isProgrammaticChange = true
                        rewriteTextInput.setText("")
                        isProgrammaticChange = false

                        targetTextView.animate()
                            .alpha(0f)
                            .setDuration(300)
                            .withEndAction {
                                targetTextView.visibility = View.GONE
                                targetTextView.text = getString(R.string.all_words_completed)
                            }
                            .start()

                        rewriteTextInput.isEnabled = false
                        rewriteTextInput.hint = getString(R.string.text_rewrite_complete)
                    }
                }
            }
        })

        // Disable copy/paste using the reusable callback
        rewriteTextInput.customSelectionActionModeCallback = disableActionModeCallback
        rewriteTextInput.customInsertionActionModeCallback = disableActionModeCallback

        // Disable long press
        rewriteTextInput.setOnLongClickListener { true }
    }

    private fun setupCheckbox(){
        behavior.attachCheckboxListener(checkbox)
    }

    private fun updateDragStatus() {
        if(behavior.dragCompleted){
            dragStatusText.text = getString(R.string.drag_completed)
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_green_dark, null))
            dragStatusText.visibility = View.VISIBLE
        }
        else if(behavior.dragAttempts > 0){
            dragStatusText.text = getString(R.string.drag_try_again)
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_red_dark, null))
            dragStatusText.visibility = View.VISIBLE
        }
    }

    private fun setupSubmitButton() {
        submitButton.setOnClickListener {
            if (validator.validateSubmission(
                    dragCompleted = behavior.dragCompleted,
                    allWordsCompleted = currentWordIndex >= targetWords.size,
                    checkbox = checkbox
                )) {
                submitButton.isEnabled = false
                submitButton.text = getString(R.string.saving)
                repo.ensureAnonAuth(
                    onReady = { submitToFirebase() },
                    onError = { error ->
                        Toast.makeText(this, error, Toast.LENGTH_LONG).show()
                        submitButton.isEnabled = true
                        submitButton.text = getString(R.string.submit)
                    }
                )
            }
        }
    }

    private fun submitToFirebase(){
        if (isAuthenticationMode) {
            // Zatiaľ len zobraz message a choď na ending screen
            Toast.makeText(
                this,
                "Autentifikácia done",
                Toast.LENGTH_LONG
            ).show()

            // TODO: Tu bude neskôr ML predikcia

            goToFinalScreen()
            return
        }

        val userIdStr = userId.orEmpty()

        repo.saveSubmission(
            userId = userIdStr,
            submissionNumber = submissionNumber,
            dragAttempts = behavior.dragAttempts,
            dragDistance = behavior.dragDistance,
            dragPathLength = behavior.dragPathLength,
            dragDurationSec = behavior.getDragDurationSec(),
            textRewriteTime = behavior.getTextRewriteTime(),
            averageWordTime = behavior.getAverageWordCompletionTime(),
            textEditCount = behavior.textEditCount,
            touchPointsCount = behavior.getTouchPoints().size,
            touchPoints = behavior.getTouchPoints(),
            keystrokes = behavior.getKeystrokes(),
            sensorDataCount = sensorCollector.getSensorData().size,
            sensorData = sensorCollector.getSensorData(),
            submissionDurationSec = behavior.getSubmissionDurationSec(),
            onSuccess = {
                Toast.makeText(this, getString(R.string.submission_saved, submissionNumber), Toast.LENGTH_SHORT).show()

                if(submissionNumber < 15)
                    goToNextSubmission(userIdStr, submissionNumber + 1)
                else
                    goToFinalScreen()
            },
            onError = { eMsg ->
                Toast.makeText(this, eMsg, Toast.LENGTH_LONG).show()
                submitButton.isEnabled = true
                submitButton.text = getString(R.string.submit)
            }
        )
    }

    private fun goToNextSubmission(userId: String, nextSubmissionNumber: Int) {
        val intent = Intent(this, SubmissionActivity::class.java).apply{
            putExtra("userId", userId)
            putExtra("submissionNumber", nextSubmissionNumber)
        }
        startActivity(intent)
        finish()
    }

    private fun goToFinalScreen() {
        startActivity(Intent(this, EndingActivity::class.java))
        finish()
    }
}
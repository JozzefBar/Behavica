package com.example.behavica.ui

import android.content.Intent
import android.os.Bundle
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
import com.example.behavica.sensors.HandDetector
import com.example.behavica.validation.SubmissionValidator
import com.google.android.material.textfield.TextInputEditText
import com.google.firebase.auth.FirebaseAuth
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
    private val auth by lazy { FirebaseAuth.getInstance() }

    private var userId: String? = null
    private var submissionNumber: Int = 1

    private lateinit var behavior: BehaviorTracker
    private lateinit var hand: HandDetector
    private lateinit var repo: FirestoreRepository
    private lateinit var validator: SubmissionValidator

    private val targetText = "Behavica"

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

        initViews()
        submissionTitle.text = "Submission $submissionNumber of 5"
        targetTextView.text = "Copy this text: \"$targetText\""

        behavior = BehaviorTracker()
        hand = HandDetector(this).also { it.start() }
        repo = FirestoreRepository(db)
        validator = SubmissionValidator()

        behavior.onDragStatusChanged = { completed ->
            runOnUiThread { updateDragStatus() }
        }

        setupDragTest()
        setupTextInput()
        setupCheckbox()
        setupSubmitButton()

        behavior.attachTouchListener(rewriteTextInput, "copyTextInput")
        behavior.attachTouchListener(checkbox, "checkBox")
        behavior.attachTouchListener(submitButton, "submitButton")

        val callback = object : OnBackPressedCallback(true) { override fun handleOnBackPressed() {} }
        onBackPressedDispatcher.addCallback(this, callback)
    }

    override fun onDestroy(){
        super.onDestroy()
        hand.stop()
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
        behavior.attachTextWatcher(rewriteTextInput)

        // Disable copy/paste
        rewriteTextInput.customSelectionActionModeCallback = object : android.view.ActionMode.Callback {
            override fun onCreateActionMode(mode: android.view.ActionMode?, menu: android.view.Menu?): Boolean = false
            override fun onPrepareActionMode(mode: android.view.ActionMode?, menu: android.view.Menu?): Boolean = false
            override fun onActionItemClicked(mode: android.view.ActionMode?, item: android.view.MenuItem?): Boolean = false
            override fun onDestroyActionMode(mode: android.view.ActionMode?) {}
        }

        rewriteTextInput.customInsertionActionModeCallback = object : android.view.ActionMode.Callback {
            override fun onCreateActionMode(mode: android.view.ActionMode?, menu: android.view.Menu?): Boolean = false
            override fun onPrepareActionMode(mode: android.view.ActionMode?, menu: android.view.Menu?): Boolean = false
            override fun onActionItemClicked(mode: android.view.ActionMode?, item: android.view.MenuItem?): Boolean = false
            override fun onDestroyActionMode(mode: android.view.ActionMode?) {}
        }

        // Disable long press
        rewriteTextInput.setOnLongClickListener { true }

    }

    private fun setupCheckbox(){
        behavior.attachCheckboxListener(checkbox)
    }

    private fun updateDragStatus() {
        if(behavior.dragCompleted){
            dragStatusText.text = "✓ Drag test completed!"
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_green_dark, null))
            dragStatusText.visibility = View.VISIBLE
        }
        else if(behavior.dragAttempts > 0){
            dragStatusText.text = "Please try again - drag the circle all the way to B"
            dragStatusText.setTextColor(resources.getColor(android.R.color.holo_red_dark, null))
            dragStatusText.visibility = View.VISIBLE
        }
    }

    private fun setupSubmitButton() {
        submitButton.setOnClickListener {
            if (validator.validateSubmission(
                    dragCompleted = behavior.dragCompleted,
                    textInput = rewriteTextInput,
                    targetText = targetText,
                    checkbox = checkbox
                )) {
                submitButton.isEnabled = false
                submitButton.text = "Saving..."
                ensureAnonAuthThen { submitToFirebase() }
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
                submitButton.isEnabled = true
                submitButton.text = "Submit"
            }
    }

    private fun submitToFirebase(){
        val userIdStr = userId.orEmpty()

        val textRewriteCompleted = rewriteTextInput.text.toString().trim() == targetText

        repo.saveSubmission(
            userId = userIdStr,
            submissionNumber = submissionNumber,
            handHeld = hand.currentHand(),
            dragCompleted = behavior.dragCompleted,
            dragAttempts = behavior.dragAttempts,
            dragDistance = behavior.dragDistance,
            dragPathLength = behavior.dragPathLength,
            dragDurationSec = behavior.getDragDurationSec(),
            textRewriteCompleted = textRewriteCompleted,
            textRewriteTime = behavior.getTextRewriteTime(),
            textEditCount = behavior.textEditCount,
            checkboxChecked = behavior.checkboxChecked,
            touchPoints = behavior.getTouchPoints(),
            keystrokes = behavior.getKeystrokes(),
            onSuccess = {
                Toast.makeText(this, "Submission $submissionNumber saved!", Toast.LENGTH_SHORT).show()

                if(submissionNumber < 5)
                    goToNextSubmission(userIdStr, submissionNumber + 1)
                else
                    goToFinalScreen()
            },
            onError = { eMsg ->
                Toast.makeText(this, eMsg, Toast.LENGTH_LONG).show()
                submitButton.isEnabled = true
                submitButton.text = "Submit"
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
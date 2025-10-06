package com.example.behavica.logging

import android.annotation.SuppressLint
import android.text.Editable
import android.text.TextWatcher
import android.view.MotionEvent
import android.view.View
import android.widget.AdapterView
import android.widget.Button
import android.widget.CheckBox
import android.widget.Spinner
import com.example.behavica.metrics.FormMetrics
import com.example.behavica.model.TouchPoint
import com.google.android.material.textfield.TextInputEditText
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

class BehaviorTracker(private val metrics: FormMetrics) {
    private val touchPoints = mutableListOf<TouchPoint>()

    private lateinit var userIdInput: TextInputEditText
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkBox: CheckBox
    private lateinit var submitButton: Button

    fun attach(
        inputId: TextInputEditText,
        inputAge: TextInputEditText,
        spinner: Spinner,
        checkbox: CheckBox,
        submit: Button,
    ){
        userIdInput = inputId
        userAgeInput = inputAge
        genderSpinner = spinner
        checkBox = checkbox
        submitButton = submit

        setupBehaviorTracking()
    }

    fun getTouchPoints(): List<TouchPoint> = touchPoints.toList()

    @SuppressLint("ClickableViewAccessibility")
    private fun setupBehaviorTracking() {

        //function for touch recording
        fun addTouchListener(view: View, targetName: String) {
            view.setOnTouchListener { _, event ->
                if (event.action == MotionEvent.ACTION_DOWN) {
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
                if (metrics.userIdStartTime == 0L) metrics.userIdStartTime = System.currentTimeMillis()
                metrics.userIdEditCount++
                metrics.userIdMaxLength = maxOf(metrics.userIdMaxLength, s?.length ?: 0)
            }

            override fun afterTextChanged(s: Editable?) {
                metrics.userIdEndTime = System.currentTimeMillis()
            }
        })

        // Track userAge input
        userAgeInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                if (metrics.userAgeStartTime == 0L) metrics.userAgeStartTime = System.currentTimeMillis()
                metrics.userAgeEditCount++
            }

            override fun afterTextChanged(s: Editable?) {
                metrics.userAgeEndTime = System.currentTimeMillis()
            }
        })

        // Track gender spinner clicks
        genderSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (position > 0 && metrics.genderSelectTime == 0L) {
                    metrics.genderSelectTime = System.currentTimeMillis()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        // Track checkbox clicks
        checkBox.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && metrics.checkboxClickTime == 0L) {
                metrics.checkboxClickTime = System.currentTimeMillis()
            }
        }

        addTouchListener(userIdInput, "userIdInput")
        addTouchListener(userAgeInput, "userAgeInput")
        addTouchListener(genderSpinner, "genderSpinner")
        addTouchListener(checkBox, "checkBox")
        addTouchListener(submitButton, "submitButton")
    }
}
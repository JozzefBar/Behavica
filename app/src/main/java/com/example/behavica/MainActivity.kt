package com.example.behavica

import android.content.Intent
import android.os.Bundle
import android.widget.*
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

class MainActivity : AppCompatActivity() {

    private lateinit var userIdLayout: TextInputLayout
    private lateinit var userIdInput: TextInputEditText
    private lateinit var userAgeLayout: TextInputLayout
    private lateinit var userAgeInput: TextInputEditText
    private lateinit var genderSpinner: Spinner
    private lateinit var checkBox: CheckBox
    private lateinit var submitButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContentView(R.layout.activity_main)

        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.afterSubmit)) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        initViews()
        setupGenderSpinner()
        setupSubmitButton()
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
            if(validateForm())
                submitForm()
        }
    }


    private fun validateForm(): Boolean {
        val userId = userIdInput.text.toString().trim()
        if(userId.isEmpty()) {
            userIdLayout.error = "Please enter a valid user id"
            return false
        }

        val userAge = userAgeInput.text.toString().trim()
        if(userAge.isEmpty()){
            userAgeLayout.error = "Please enter a valid user age"
            return false
        }

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

    private fun submitForm() {
        val userId = userIdInput.text.toString().trim()
        val userAge = userAgeInput.text.toString().trim()
        val userGender = genderSpinner.selectedItem.toString()

        Toast.makeText(this, "Form submitted successfully!\nUserID: $userId\nAge: $userAge\nGender: $userGender", Toast.LENGTH_LONG
        ).show()

        val intent = Intent(this, AfterSubmitActivity::class.java)
        startActivity(intent)

        finish()
    }
}
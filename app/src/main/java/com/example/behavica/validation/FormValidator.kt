package com.example.behavica.validation

import android.widget.CheckBox
import android.widget.Spinner
import android.widget.Toast
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

class FormValidator(
    private val userIdLayout: TextInputLayout,
    private val userAgeLayout: TextInputLayout,
    private val genderSpinner: Spinner,
    private val checkBox: CheckBox
) {
    fun validateForm(): Boolean {
        val userId = (userIdLayout.editText as TextInputEditText).text.toString().trim()
        if (userId.isEmpty()) {
            userIdLayout.error = "Please enter a valid user id"
            return false
        }
        if (userId.count() != 5) {
            userIdLayout.error = "Please user id must contain 5 characters"
            return false
        }
        userIdLayout.error = null

        val ageStr = (userAgeLayout.editText as TextInputEditText).text.toString().trim()
        if (ageStr.isEmpty()) {
            userAgeLayout.error = "Please enter a valid user age"
            return false
        }
        val userAge = ageStr.toInt()
        if (userAge < 10 || userAge > 100) {
            userAgeLayout.error = "Please age must be between 10 and 100"
            return false
        }
        userAgeLayout.error = null

        if (genderSpinner.selectedItemPosition == 0) {
            Toast.makeText(userIdLayout.context, "Please select your gender", Toast.LENGTH_LONG).show()
            return false
        }
        if (!checkBox.isChecked) {
            Toast.makeText(userIdLayout.context, "You must agree to biometric data collection", Toast.LENGTH_LONG).show()
            return false
        }
        return true
    }
}
package com.example.behavica.validation

import android.widget.CheckBox
import android.widget.Spinner
import android.widget.Toast
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

class FormValidator(
    private val userAgeLayout: TextInputLayout,
    private val genderSpinner: Spinner,
    private val checkBox: CheckBox
) {
    fun validateForm(): Boolean {
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

        //layout for text not correct
        if (genderSpinner.selectedItemPosition == 0) {
            Toast.makeText(userAgeLayout.context, "Please select your gender", Toast.LENGTH_LONG).show()
            return false
        }
        if (!checkBox.isChecked) {
            Toast.makeText(userAgeLayout.context, "You must agree to biometric data collection", Toast.LENGTH_LONG).show()
            return false
        }
        return true
    }
}
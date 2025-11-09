// MetadataValidator.kt
package com.example.behavica.validation

import android.widget.Spinner
import android.widget.CheckBox
import android.widget.Toast
import com.google.android.material.textfield.TextInputLayout

class MetadataValidator(
    private val userAgeLayout: TextInputLayout,
    private val genderSpinner: Spinner,
    private val checkBox: CheckBox
) {
    data class ValidationResult(
        val isValid: Boolean,
        val errorMessage: String = ""
    )

    fun validateMetadata(ageStr: String): ValidationResult  {
        // Validate age
        if (ageStr.isEmpty()) {
            userAgeLayout.error = "Please enter your age"
            return ValidationResult(false, "Please enter your age")
        }
        val userAge = ageStr.toIntOrNull()
        if (userAge == null || userAge < 10 || userAge > 100) {
            userAgeLayout.error = "Age must be between 10 and 100"
            return ValidationResult(false, "Age must be between 10 and 100")
        }
        userAgeLayout.error = null

        // Validate gender
        if (genderSpinner.selectedItemPosition == 0) {
            Toast.makeText(userAgeLayout.context, "Please select your gender", Toast.LENGTH_LONG).show()
            return ValidationResult(false, "Please select your gender")
        }

        // Validate checkbox
        if (!checkBox.isChecked) {
            return ValidationResult(false, "You must agree to data collection")
        }

        return ValidationResult(true)
    }
}
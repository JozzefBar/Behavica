// MetadataValidator.kt
package com.example.behavica.validation

import android.widget.Spinner
import android.widget.CheckBox
import android.widget.Toast
import com.example.behavica.R
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
        val context = userAgeLayout.context

        // Validate age
        if (ageStr.isEmpty()) {
            userAgeLayout.error = context.getString(R.string.please_enter_age)
            return ValidationResult(false, context.getString(R.string.please_enter_age))
        }
        val userAge = ageStr.toIntOrNull()
        if (userAge == null || userAge < 10 || userAge > 100) {
            userAgeLayout.error = context.getString(R.string.age_must_be_between)
            return ValidationResult(false, context.getString(R.string.age_must_be_between))
        }
        userAgeLayout.error = null

        // Validate gender
        if (genderSpinner.selectedItemPosition == 0) {
            Toast.makeText(context, R.string.please_select_gender, Toast.LENGTH_LONG).show()
            return ValidationResult(false, context.getString(R.string.please_select_gender))
        }

        // Validate checkbox
        if (!checkBox.isChecked) {
            return ValidationResult(false, context.getString(R.string.must_agree_data_collection))
        }

        return ValidationResult(true)
    }
}
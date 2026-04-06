package com.example.behavica.validation

import android.widget.Spinner
import android.widget.CheckBox
import android.widget.Toast
import com.example.behavica.R
import com.google.android.material.textfield.TextInputLayout

class MetadataValidator(
    private val userAgeLayout: TextInputLayout,
    private val genderSpinner: Spinner,
    private val dominantHandSpinner: Spinner,
    private val checkBox: CheckBox
) {
    fun validateMetadata(ageStr: String): Boolean {
        val context = userAgeLayout.context

        // Validate age
        if (ageStr.isEmpty()) {
            userAgeLayout.error = context.getString(R.string.please_enter_age)
            return false
        }
        val userAge = ageStr.toIntOrNull()
        if (userAge == null || userAge < 10 || userAge > 100) {
            userAgeLayout.error = context.getString(R.string.age_must_be_between)
            return false
        }
        userAgeLayout.error = null

        // Validate gender
        if (genderSpinner.selectedItemPosition == 0) {
            Toast.makeText(context, R.string.please_select_gender, Toast.LENGTH_LONG).show()
            return false
        }

        // Validate dominant hand
        if (dominantHandSpinner.selectedItemPosition == 0) {
            Toast.makeText(context, R.string.please_select_dominant_hand, Toast.LENGTH_LONG).show()
            return false
        }

        // Validate checkbox
        if (!checkBox.isChecked) {
            Toast.makeText(context, R.string.must_agree_data_collection, Toast.LENGTH_LONG).show()
            return false
        }

        return true
    }
}
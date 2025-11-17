package com.example.behavica.validation

import android.widget.CheckBox
import android.widget.Toast
import com.example.behavica.R

class SubmissionValidator{
    fun validateSubmission(
        dragCompleted: Boolean,
        allWordsCompleted: Boolean,
        checkbox: CheckBox
    ):Boolean{
        val context = checkbox.context

        if(!dragCompleted) {
            Toast.makeText(context, R.string.please_complete_drag, Toast.LENGTH_LONG).show()
            return false
        }

        if(!allWordsCompleted){
            Toast.makeText(context, R.string.please_rewrite_all_words, Toast.LENGTH_LONG).show()
            return false
        }

        if (!checkbox.isChecked) {
            Toast.makeText(context, R.string.must_agree_data_collection, Toast.LENGTH_LONG).show()
            return false
        }

        return true
    }
}
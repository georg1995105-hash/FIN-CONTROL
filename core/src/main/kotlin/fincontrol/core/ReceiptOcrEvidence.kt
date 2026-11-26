package fincontrol.core

/** Only OCR-observed source values, always requiring explicit review. */
object ReceiptOcrEvidence {
    private val money=Regex("""(?<![\p{L}\d,.+\-])(?:\d{1,3}(?:[ \u00a0]\d{3}){1,2}|\d{1,7})[,.]\d{2}(?![\w,.])""")
    private val nonFinal=Regex("""^(?:(?:ИТОГО|ВСЕГО)\s+(?:НДС|НАЛОГ|СКИДКИ|СКИДКА|ТОВАРОВ|ПОЗИЦИЙ)|НДС|НАЛОГ|СКИДКА|СДАЧА|ВОЗВРАТ|ОПЛАТА|НАЛИЧНЫМИ|БЕЗНАЛИЧНЫМИ|ПОЛУЧЕНО|ПОДЫТОГ|ПРЕДОПЛАТА)(?:\b|\s|:)""")
    private val label=Regex("""^(?:ИТОГО(?:\s+К\s+ОПЛАТЕ)?|ВСЕГО(?:\s+К\s+ОПЛАТЕ)?|К\s+ОПЛАТЕ|СУММА\s+К\s+ОПЛАТЕ|ОБЩАЯ\s+СУММА)(?:\b|\s|:|=)""")
    fun build(revision:Long, lines:List<OcrSourceLine>):TotalReviewInput {
        require(revision>0 && lines.size<=3000)
        require(lines.map { it.sourceIndex }.distinct().size==lines.size)
        data class Found(val choice:ObservedTotalChoice,val priority:Int)
        val results=mutableListOf<Found>()
        for (line in lines) {
            require(line.sourceIndex>=0 && line.box.isValid() && line.rawText.length in 1..2048)
            require(line.confidenceBasisPoints in 0..10000)
            if (line.confidenceBasisPoints<8500) continue
            val normalized=line.rawText.trim().uppercase(java.util.Locale.ROOT).replace('Ё','Е')
            if (nonFinal.containsMatchIn(normalized)) continue
            val priority=if(label.containsMatchIn(normalized)) 1 else 0
            for(hit in money.findAll(line.rawText)) {
                val value=hit.value.replace(" ","").replace("\u00a0","").replace('.',',')
                if(!Regex("""\d{1,7},\d{2}""").matches(value))continue
                results+=Found(ObservedTotalChoice(value,line.sourceIndex,0,OcrAmountRole.UNKNOWN),priority)
            }
        }
        // Display order only: no inferred rank, no preselection, no automatic approval.
        val choices=results.distinctBy { it.choice.sourceIndex to it.choice.observedAmount }
            .sortedWith(compareByDescending<Found> { it.priority }.thenByDescending { it.choice.sourceIndex })
            .take(8).map { it.choice }
        return TotalReviewInput(revision,if(choices.isEmpty()) TotalReviewMode.NEEDS_RECAPTURE
            else TotalReviewMode.AMBIGUOUS_REVIEW,lines,choices)
    }
}

# How Etude teaches

Etude's design follows learning techniques with strong research support.
This document records each principle, the evidence for it, and how the
application puts it into practice, so that contributors can keep new
features consistent with it.

A good overview of the evidence is Dunlosky et al. (2013), who rate
*practice testing* and *distributed practice* as the two techniques of
highest utility across ages, materials and settings.

## Principles

### Retrieval practice

Recalling something strengthens memory more than re-reading it (the
testing effect; Roediger & Karpicke, 2006).

*In Etude:* every exercise asks the learner to produce or recognise an
answer. Theory lessons end with "check your understanding" questions
instead of a summary to re-read.

### Spaced repetition

Reviews spread out over increasing intervals beat the same amount of
practice massed together (Cepeda et al., 2006).

*In Etude:* every knowledge item has an FSRS card (Ye, Su & Cao, 2022).
The daily **Today** session reviews the items that are due across all
exercises. Learners never rate themselves: the rating is derived from
correctness, hints and response time relative to the learner's own speed
(`etude/learning/rating.py`).

### Interleaving

Mixing similar categories during practice improves the ability to tell
them apart, even though it feels harder than practising one category at a
time (Rohrer & Taylor, 2007; Carvalho & Goldstone, 2014). Interleaved
practice has also benefited music performance learning (Carter & Grahn,
2016).

*In Etude:* review sessions mix exercises and deliberately place
confusable items (minor and major sixths, the tritone and the perfect
fifth, deceptive and authentic cadences) close together.

### Desirable difficulty

Learning is fastest when about 85 % of answers are correct (Wilson et al.,
2019).

*In Etude:* new items are introduced while the learner's rolling accuracy
stays above the target, and difficulty parameters (range, clefs,
accidentals, tempo) grow with mastery.

### Elaborated, immediate feedback

Feedback that explains *why* an answer is right or wrong is more effective
than a bare verdict (Hattie & Timperley, 2007; Shute, 2008).

*In Etude:* every graded answer comes with an explanation, and ear-training
feedback lets the learner play their answer and the correct one side by
side.

### Mastery learning

Moving on only after a unit is mastered, with corrective practice for
those who have not yet mastered it, produces large gains (Bloom, 1984).

*In Etude:* units unlock when 80 % of their items reach an accuracy and
FSRS stability threshold, and each level ends with a level exam that is
passed with 80 % correct answers (mastery criteria are commonly set at
80–90 %). Locks are advice: lessons are always readable, and a locked unit
can be practised after a confirmation (autonomy, see below).

### Dual coding and multimedia

Combining words, pictures and sound supports understanding when they
present the same idea together (Paivio, 1986; Mayer, 2009).

*In Etude:* notation and sound appear together: eye exercises can play
what is written and ear exercises can show the staff after answering.

### Worked examples and fading

Novices learn more from studying worked examples than from solving
problems unaided; guidance should then fade (Sweller & Cooper, 1985;
Renkl & Atkinson, 2003).

*In Etude:* lessons move from a worked example, to a completion problem,
to an independent problem.

### Perceptual learning

Expert perception develops through many varied classification trials
with feedback (Kellman & Garrigan, 2009).

*In Etude:* questions vary everything except the concept being learned,
and ear training includes contrast trials (same root, two candidate
answers) before free identification.

### Pretesting

Attempting questions before instruction improves later learning, even
when the attempts fail (Richland, Kornell & Kao, 2009).

*In Etude:* the placement test seeds the scheduler so experienced learners
skip what they know: it asks five questions about what each unit adds,
places the learner out of every unit answered at 80 % or better, and stops
at the first unit that is not. Lessons may open with a question.

### Motivation without manipulation

Autonomy, competence and relatedness sustain motivation; controlling
rewards undermine it (Deci & Ryan, 2000).

*In Etude:* a daily goal and a gentle streak, visible progress, and no
guilt-inducing notifications or artificial loss of progress.

## References

* Bloom, B. S. (1984). The 2 sigma problem: The search for methods of group
  instruction as effective as one-to-one tutoring. *Educational
  Researcher*, 13(6), 4–16.
* Carter, C. E., & Grahn, J. A. (2016). Optimizing music learning:
  Exploring how blocked and interleaved practice schedules affect advanced
  performance. *Frontiers in Psychology*, 7, 1251.
* Carvalho, P. F., & Goldstone, R. L. (2014). Putting category learning in
  order: Category structure and temporal arrangement affect the benefit of
  interleaved over blocked study. *Memory & Cognition*, 42(3), 481–495.
* Cepeda, N. J., Pashler, H., Vul, E., Wixted, J. T., & Rohrer, D. (2006).
  Distributed practice in verbal recall tasks: A review and quantitative
  synthesis. *Psychological Bulletin*, 132(3), 354–380.
* Deci, E. L., & Ryan, R. M. (2000). The "what" and "why" of goal pursuits:
  Human needs and the self-determination of behavior. *Psychological
  Inquiry*, 11(4), 227–268.
* Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham,
  D. T. (2013). Improving students' learning with effective learning
  techniques. *Psychological Science in the Public Interest*, 14(1), 4–58.
* Hattie, J., & Timperley, H. (2007). The power of feedback. *Review of
  Educational Research*, 77(1), 81–112.
* Kellman, P. J., & Garrigan, P. (2009). Perceptual learning and human
  expertise. *Physics of Life Reviews*, 6(2), 53–84.
* Mayer, R. E. (2009). *Multimedia learning* (2nd ed.). Cambridge
  University Press.
* Paivio, A. (1986). *Mental representations: A dual coding approach*.
  Oxford University Press.
* Renkl, A., & Atkinson, R. K. (2003). Structuring the transition from
  example study to problem solving in cognitive skill acquisition: A
  cognitive load perspective. *Educational Psychologist*, 38(1), 15–22.
* Richland, L. E., Kornell, N., & Kao, L. S. (2009). The pretesting effect:
  Do unsuccessful retrieval attempts enhance learning? *Journal of
  Experimental Psychology: Applied*, 15(3), 243–257.
* Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning: Taking
  memory tests improves long-term retention. *Psychological Science*,
  17(3), 249–255.
* Rohrer, D., & Taylor, K. (2007). The shuffling of mathematics problems
  improves learning. *Instructional Science*, 35(6), 481–498.
* Shute, V. J. (2008). Focus on formative feedback. *Review of Educational
  Research*, 78(1), 153–189.
* Sweller, J., & Cooper, G. A. (1985). The use of worked examples as a
  substitute for problem solving in learning algebra. *Cognition and
  Instruction*, 2(1), 59–89.
* Wilson, R. C., Shenhav, A., Straccia, M., & Cohen, J. D. (2019). The
  Eighty Five Percent Rule for optimal learning. *Nature Communications*,
  10, 4646.
* Ye, J., Su, J., & Cao, Y. (2022). A stochastic shortest path algorithm for
  optimizing spaced repetition scheduling. *Proceedings of the 28th ACM
  SIGKDD Conference on Knowledge Discovery and Data Mining*, 4381–4390.

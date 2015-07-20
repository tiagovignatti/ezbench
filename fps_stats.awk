#!/usr/bin/awk -f

BEGIN {
	min = 10000000
}

{
	val = $1

	if (val < min)
		min = val
	if (val > max)
		max = val
	sum += val
	sum2 += val * val 

	# percentiles
	array[NR] = val
}

END {
	avg = sum / NR

	if (NR > 1)
            var= ((sum*sum) - sum2)/(NR-1)
        else
            var=0

	qsort(array, 1, NR)

	p50 = int(NR / 2)
	p90 = int(NR * 0.9)
	p95 = int(NR * 0.95)
	p99 = int(NR * 0.99)

	print avg " min/p50/90/95/99/max/std = " min " / " array[p50] " / " array[p90] " / " array[p95] " / " array[p99] " / " max " / " sqrt(var) " n=" NR
}

function qsort(A, left, right,   i, last) {
	if (left >= right)
		return
	swap(A, left, left+int((right-left+1)*rand()))
	last = left
	for (i = left+1; i <= right; i++)
		if (A[i] < A[left])
			swap(A, ++last, i)
	swap(A, left, last)
	qsort(A, left, last-1)
	qsort(A, last+1, right)
}
function swap(A, i, j,   t) {
	t = A[i]; A[i] = A[j]; A[j] = t
}

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
}

END {
	avg = sum / NR
	var= ((sum*sum) - sum2)/(NR-1)

	print avg " std=" sqrt(var) " n=" NR
}
